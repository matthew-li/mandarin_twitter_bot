from aws_client import AWSClientError
from aws_client import batch_put_items
from aws_client import get_and_delete_unprocessed_word
from aws_client import get_earliest_tweet_date
from aws_client import get_tweets_on_date
from aws_client import put_item
from aws_client import validate_item_against_schema
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import date
from http import HTTPStatus
from settings import AWS_DYNAMODB_ENDPOINT_URL
from utils import utc_seconds_since_the_epoch
import boto3
import botocore
import unittest
import warnings

"""A test module for aws_client.py."""


class TestDynamoDBMixin(unittest.TestCase):
    """A class that provides setup and teardown for tests that access
    and modify AWS DynamoDB."""

    def setUp(self):
        # Ignore some warnings about an unclosed socket caused by boto3
        # (https://github.com/boto/boto3/issues/454).
        messages_to_ignore = [
            "unclosed.*<ssl.SSLSocket.*>",
            "unclosed.*<socket.socket.*>",
        ]
        for message in messages_to_ignore:
            warnings.filterwarnings(
                "ignore", category=ResourceWarning, message=message)

        # Store a mapping from table name to a list of keys for created
        # items so that they can be deleted during teardown.
        self.created_items = {
            DynamoDBTable.SETTINGS.value.name: [],
            DynamoDBTable.TWEETS.value.name: [],
            DynamoDBTable.UNPROCESSED_WORDS.value.name: [],
        }

    def tearDown(self):
        # Delete created items.
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        for table_name, keys in self.created_items.items():
            table = dynamodb.Table(table_name)
            with table.batch_writer() as batch:
                for key in keys:
                    batch.delete_item(key)


class TestAWSClient(TestDynamoDBMixin):
    """A class for testing the methods of aws_client."""

    def test_tables_exist(self):
        """Test that the expected tables exist in DynamoDB."""
        try:
            dynamodb = boto3.client(
                AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
            tables = dynamodb.list_tables()
        except botocore.exceptions.EndpointConnectionError:
            raise AWSClientError(
                f"The endpoint {AWS_DYNAMODB_ENDPOINT_URL} is not running.")
        actual_table_names = set(tables["TableNames"])
        expected_table_names = set()
        for table in DynamoDBTable:
            expected_table_names.add(table.value.name)
        self.assertEqual(expected_table_names, actual_table_names)

    def test_batch_put_items_raises_errors(self):
        """Test that the method for putting items in a batch raises the
        expected errors."""
        valid_item = {
            "Id": "",
            "TweetId": "",
            "Date": "",
            "DateEntry": 0,
            "Word": "",
        }
        arg_sets = [
            ("table", []),
            (DynamoDBTable.TWEETS, valid_item),
            (DynamoDBTable.TWEETS, [valid_item, []]),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(TypeError):
                batch_put_items(arg_set[0], arg_set[1])
        table = DynamoDBTable.TWEETS
        schema = table.value.schema
        self.assertTrue(validate_item_against_schema(schema, valid_item))
        invalid_item = valid_item.copy()
        invalid_item.pop("Word")
        self.assertFalse(validate_item_against_schema(schema, invalid_item))
        items = [valid_item, invalid_item]
        try:
            batch_put_items(table, items)
        except ValueError as e:
            e = str(e)
            self.assertIn("does not conform to the schema.", e)
            self.assertNotIn("Word", e)
        else:
            self.fail("A ValueError should have been raised.")

    def test_batch_put_items_performs_update(self):
        """Test that the method for putting items in a batch updates the
        table as expected."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        field_sets = [
            ("0", "abc", "abc"),
            ("1", "def", "def"),
            ("2", "ghi", "ghi"),
        ]
        items = []
        for field_set in field_sets:
            items.append({
                "Id": field_set[0],
                "Characters": field_set[1],
                "Pinyin": field_set[2],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            })

        batch_put_items(table, items)

        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        unprocessed_words = dynamodb.Table(table.value.name)
        self.assertEqual(unprocessed_words.item_count, len(items))
        found_items = []
        for i in range(len(items)):
            found_items.append(get_and_delete_unprocessed_word())
        found_items.sort(key=lambda x: x["Id"])

        for i in range(len(items)):
            self.assertEqual(items[i], found_items[i])

        # There should be no remaining items in the table.
        item = get_and_delete_unprocessed_word()
        self.assertFalse(item)

    def test_get_and_delete_unprocessed_word(self):
        """Test that the method for retrieving an UnprocessedWord
        returns the word and deletes it from the table."""
        table = DynamoDBTable.UNPROCESSED_WORDS

        # Add an item that conforms to the schema.
        valid_item = {
            "Id": "0",
            "Characters": "abc",
            "Pinyin": "abc",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, valid_item)

        # Add an item that does not conform to the schema.
        invalid_item = {
            "Id": "1",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        unprocessed_words = dynamodb.Table(table.value.name)
        unprocessed_words.put_item(Item=invalid_item)

        for _ in range(2):
            try:
                item = get_and_delete_unprocessed_word()
            except ValueError as e:
                e = str(e)
                error = f"does not conform to the schema."
                self.assertIn(error, e)
                self.assertIn(f"'Id': '{invalid_item['Id']}'", e)
            else:
                self.assertEqual(len(item), len(valid_item))
                for key in item:
                    self.assertEqual(item[key], valid_item[key])

        # The items should be deleted, and there should be none left.
        self.assertEqual(get_and_delete_unprocessed_word(), {})
        response = unprocessed_words.scan(Limit=1)
        self.assertFalse(response["Items"])

    def test_get_earliest_tweet_date(self):
        """Test that the method for returning the date of the earliest
        Tweet returns the expected value."""
        # The setting is initially unset, so the method should return None.
        self.assertIsNone(get_earliest_tweet_date())

        table = DynamoDBTable.SETTINGS
        item = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": "1970-01-01",
        }
        put_item(table, item)
        self.created_items[table.value.name].append({"Name": item["Name"]})

        # The setting is set, so the method should return its value.
        self.assertEqual(get_earliest_tweet_date(), item["Value"])

    def test_get_tweets_on_date_raises_errors(self):
        """Test that the method for retrieving Tweets tweeted on a given
        date raises the expected errors."""
        try:
            get_tweets_on_date("date", date_entry=None)
        except TypeError as e:
            self.assertEqual(str(e), "Date date is not a date object.")
        else:
            self.fail("A TypeError should have been raised.")

        try:
            get_tweets_on_date(date.today(), date_entry="integer")
        except TypeError as e:
            self.assertEqual(str(e), "Date entry integer is not an integer.")
        else:
            self.fail("A TypeError should have been raised.")

        for date_entry in (-1, TWEETS_PER_DAY):
            try:
                get_tweets_on_date(date.today(), date_entry=date_entry)
            except ValueError as e:
                self.assertEqual(str(e), f"Invalid date entry {date_entry}.")
            else:
                self.fail("A ValueError should have been raised.")

    def test_get_tweets_on_date_output(self):
        """Test that the method for retrieving Tweets tweeted on a given
        date returns the expected output."""
        table = DynamoDBTable.TWEETS
        field_sets = [
            ("0", "0", "1970-01-01", 0, "word0"),
            ("1", "1", "1970-01-02", 0, "word1"),
            ("2", "2", "1970-01-02", 1, "word2"),
            ("3", "3", "1970-01-02", 2, "word3"),
        ]
        items = []
        for field_set in field_sets:
            item = {
                "Id": field_set[0],
                "TweetId": field_set[1],
                "Date": field_set[2],
                "DateEntry": field_set[3],
                "Word": field_set[4],
            }
            items.append(item)
            key = {
                "Id": item["Id"],
                "Date": item["Date"],
            }
            self.created_items[table.value.name].append(key)
        batch_put_items(table, items)

        # One Tweet was tweeted on January 1st, 1970.
        january01 = date(1970, 1, 1)
        tweets = get_tweets_on_date(january01)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0], items[0])
        tweets = get_tweets_on_date(january01, date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0], items[0])
        tweets = get_tweets_on_date(january01, date_entry=1)
        self.assertEqual(len(tweets), 0)

        # Three Tweets were tweeted on January 2nd, 1970.
        january02 = date(1970, 1, 2)
        tweets = get_tweets_on_date(january02)
        self.assertEqual(len(tweets), 3)
        for i in range(3):
            self.assertEqual(tweets[i], items[i + 1])
        for i in range(3):
            tweets = get_tweets_on_date(january02, date_entry=i)
            self.assertEqual(len(tweets), 1)
            self.assertEqual(tweets[0], items[i + 1])

        # Zero Tweets were tweeted on January 3rd, 1970.
        january03 = date(1970, 1, 3)
        tweets = get_tweets_on_date(january03)
        self.assertEqual(len(tweets), 0)

        self.created_items[DynamoDBTable.SETTINGS.value.name].append(
            {"Name": DynamoDBSettings.EARLIEST_TWEET_DATE})

    def test_put_item_raises_errors(self):
        """Test that the method for putting an item raises the expected
        errors."""
        table = DynamoDBTable.TWEETS
        schema = table.value.schema
        arg_sets = [
            ("table", {}),
            (table, []),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(TypeError):
                put_item(arg_set[0], arg_set[1])
        invalid_item = {
            "Id": "",
            "TweetId": "",
            "Date": "",
            "DateEntry": 0,
        }
        self.assertFalse(validate_item_against_schema(schema, invalid_item))
        try:
            put_item(table, invalid_item)
        except ValueError as e:
            e = str(e)
            self.assertIn("does not conform to the schema.", e)
            self.assertNotIn("Word", e)
        else:
            self.fail("A ValueError should have been raised.")

    def test_put_item_performs_update(self):
        """Test that the method for putting an item updates the table as
        expected."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        field_sets = [
            ("0", "abc", "abc"),
            ("1", "def", "def"),
            ("2", "ghi", "ghi"),
        ]
        items = []
        for field_set in field_sets:
            items.append({
                "Id": field_set[0],
                "Characters": field_set[1],
                "Pinyin": field_set[2],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            })

        for item in items:
            response = put_item(table, item)
            self.assertIn("ResponseMetadata", response)
            self.assertIn("HTTPStatusCode", response["ResponseMetadata"])
            self.assertEqual(
                response["ResponseMetadata"]["HTTPStatusCode"], HTTPStatus.OK)

        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        unprocessed_words = dynamodb.Table(table.value.name)
        self.assertEqual(unprocessed_words.item_count, len(items))
        found_items = []
        for i in range(len(items)):
            found_items.append(get_and_delete_unprocessed_word())
        found_items.sort(key=lambda x: x["Id"])

        for i in range(len(items)):
            self.assertEqual(items[i], found_items[i])

        # There should be no remaining items in the table.
        item = get_and_delete_unprocessed_word()
        self.assertFalse(item)

    def test_validate_item_against_schema_raises_errors(self):
        """Test that the method for validating an item against a given
        schema raises the expected errors."""
        arg_sets = [
            ([], {}),
            ({}, []),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(TypeError):
                validate_item_against_schema(arg_set[0], arg_set[1])
        self.assertTrue(validate_item_against_schema({}, {}))

    def test_validate_item_against_schema_output(self):
        """Test that the method for validating an item against a given
        schema returns the expected output."""
        schema = DynamoDBTable.TWEETS.value.schema
        # The item and schema lengths differ.
        item = {}
        self.assertFalse(validate_item_against_schema(schema, item))
        # A key in the item has an invalid name.
        item["Id"] = "string"
        item["TweetId"] = "string"
        item["Date"] = "string"
        item["Date Entry"] = 0
        item["Word"] = "string"
        self.assertFalse(validate_item_against_schema(schema, item))
        # A value in the item has an invalid type.
        item["DateEntry"] = str(item.pop("Date Entry"))
        self.assertFalse(validate_item_against_schema(schema, item))
        # The item is correct.
        item["DateEntry"] = int(item["DateEntry"])
        self.assertTrue(validate_item_against_schema(schema, item))


if __name__ == "__main__":
    unittest.main()
