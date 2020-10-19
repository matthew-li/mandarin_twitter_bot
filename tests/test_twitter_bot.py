from aws_client import batch_put_items
from aws_client import put_item
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from datetime import date
from datetime import timedelta
from main import get_tweets_on_random_date
from settings import AWS_DYNAMODB_ENDPOINT_URL
from settings import DATE_FORMAT
from tests.test_aws_client import TestDynamoDBMixin
import boto3

"""A test module for the main functionality of the application."""


class TestTwitterBot(TestDynamoDBMixin):
    """A class for testing the main methods of the application."""

    def test_get_tweets_on_random_date(self):
        """Test that the method for retrieving the Tweets tweeted on a
        random date returns the expected output."""
        # If there was no earliest Tweet, the output should be empty.
        self.assertFalse(get_tweets_on_random_date(date_entry=0))

        earliest_tweet_date = (date.today() - timedelta(days=5))
        setting = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": earliest_tweet_date.strftime(DATE_FORMAT)
        }
        put_item(DynamoDBTable.SETTINGS, setting)

        self.assertFalse(get_tweets_on_random_date(date_entry=0))

        # Create some Tweets and check that they can be retrieved.
        table = DynamoDBTable.TWEETS
        items = []
        for i in range(5):
            item = {
                "Id": str(i),
                "TweetId": str(i),
                "Date": (earliest_tweet_date + timedelta(days=i)).strftime(
                    DATE_FORMAT),
                "DateEntry": 0,
                "Word": f"word{i}",
            }
            items.append(item)
            key = {
                "Id": item["Id"],
                "Date": item["Date"],
            }
            self.created_items[table.value.name].append(key)

        batch_put_items(table, items[:2])
        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(2)]))

        batch_put_items(table, items[2:])
        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(5)]))

        # Check that Tweets with different DateEntry values can be retrieved.
        self.assertFalse(get_tweets_on_random_date(date_entry=1))
        self.assertFalse(get_tweets_on_random_date(date_entry=2))

        items[1]["DateEntry"] = 1
        items[2]["DateEntry"] = 2
        batch_put_items(DynamoDBTable.TWEETS, items[1:3])

        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in [0, 3, 4]]))

        tweets = get_tweets_on_random_date(date_entry=1)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0]["Id"], str(1))

        tweets = get_tweets_on_random_date(date_entry=2)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0]["Id"], str(2))

        tweets = get_tweets_on_random_date(date_entry=None)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(5)]))

        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        table = dynamodb.Table(DynamoDBTable.TWEETS.value.name)
        with table.batch_writer() as batch:
            for item in items:
                key = {
                    "Id": item["Id"],
                    "Date": item["Date"],
                }
                batch.delete_item(Key=key)

        self.created_items[DynamoDBTable.SETTINGS.value.name].append(
            {"Name": DynamoDBSettings.EARLIEST_TWEET_DATE})
