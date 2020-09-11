from boto3.dynamodb.conditions import Key
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import date
from decimal import Decimal
from settings import DATE_FORMAT
import boto3
import botocore


class AWSClientError(Exception):
    """The base class for exceptions in this module."""
    pass


def batch_put_items(table, items):
    """Store the items represented by the given list of dictionaries in
    a batch write to the given table after validating that each conforms
    to the expected schema.

    Args:
        table: An instance of DynamoDBTable, which contains the table's
               name and schema.
        items: A list of dict objects representing items in the given
               table, each of which must conform to the expected schema.

    Returns:
        None.

    Raises:
        AWSClientError: If the AWS put fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If any item does not conform to the expected schema.
    """
    if not isinstance(table, DynamoDBTable):
        raise TypeError(f"Table {table} is not a DynamoDBTable object.")
    if not isinstance(items, list):
        raise TypeError(f"Items {items} is not a list object.")
    table_name = table.value.name
    table_schema = table.value.schema
    for item in items:
        if not isinstance(item, dict):
            raise TypeError(f"Item {item} is not a dict object.")
        if not validate_item_against_schema(table_schema, item):
            raise ValueError(f"Item {item} does not conform to the schema.")
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(table_name)
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
    except boto3.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")


def get_and_delete_unprocessed_word():
    """Return an UnprocessedWord after validating that it conforms to
    the expected schema. Delete it from the table.

    Args:
        None.

    Returns:
        A dictionary representing an entry in the UnprocessedWords
        table. If no words remain, return the empty dictionary.

    Raises:
        AWSClientError: If the AWS query fails.
        KeyError: If the response is missing an expected key.
        ValueError: If the returned item does not conform to the
                    expected schema.
    """
    table = DynamoDBTable.UNPROCESSED_WORDS
    table_name = table.value.name
    table_schema = table.value.schema
    item = dict()
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(table_name)
        response = table.scan(Limit=1)
        items = response["Items"]
        if not items:
            return item
        item = items[0]
        key = {
            "Id": item["Id"],
            "InsertionTimestamp": Decimal(str(item["InsertionTimestamp"])),
        }
        table.delete_item(Key=key)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    if not validate_item_against_schema(table_schema, item):
        raise ValueError(f"Item {item} does not conform to the schema.")
    return item


def get_earliest_tweet_date():
    """Return the date of the earliest Tweet stored. If this date has
    been previously stored, retrieve it from the Settings table.
    Otherwise, return None.

    Args:
        None.

    Returns:
        A string of the form "%Y-%m-%d" or None.

    Raises:
        AWSClientError: If the AWS query fails.
    """
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table_name = DynamoDBTable.SETTINGS.value.name
        table = dynamodb.Table(table_name)
        kwargs = {
            "TableName": table_name,
            "Select": "ALL_ATTRIBUTES",
            "KeyConditionExpression": Key("Name").eq(
                DynamoDBSettings.EARLIEST_TWEET_DATE)
        }
        response = table.query(**kwargs)
    except boto3.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    items = response["Items"]
    if items:
        entry = items[0]
        return entry["Value"]
    return None


def get_tweets_on_date(d, date_entry=None):
    """Return the Tweets tweeted on the date represented by the given
    date object. Optionally also filter on what number entry the tweet
    was on its date.

    Args:
        d: A date object to be used to filter Tweets on their Date
           field.
        date_entry: An integer used to filter Tweets on their DateEntry
                    field.

    Returns:
        A list of dictionaries representing entries in the Tweets table.

    Raises:
        AWSClientError: If the AWS query fails.
        KeyError: If the response is missing an expected key.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the tweet entry falls outside of the expected
                    range.
    """
    if not isinstance(d, date):
        raise TypeError(f"Date {d} is not a date object.")
    if date_entry is not None:
        if not isinstance(date_entry, int):
            raise TypeError(f"Date entry {date_entry} is not an integer.")
        if date_entry < 0 or date_entry >= TWEETS_PER_DAY:
            raise ValueError(f"Invalid date entry {date_entry}.")
    date_str = d.strftime(DATE_FORMAT)
    tweets = []
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table_name = DynamoDBTable.TWEETS.value.name
        table = dynamodb.Table(table_name)
        kwargs = {
            "TableName": table_name,
            "IndexName": "DateIndex",
            "Select": "ALL_ATTRIBUTES",
            "KeyConditionExpression": Key("Date").eq(date_str)
        }
        if date_entry is not None:
            kwargs["KeyConditionExpression"] &= Key("DateEntry").eq(date_entry)
        response = table.query(**kwargs)
        for item in response["Items"]:
            tweets.append(item)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return tweets


def put_item(table, item):
    """Store the item represented by the given dictionary in the given
    table after validating that it conforms to the expected schema.
    Return the response.

    Args:
        table: an instance of DynamoDBTable, which contains the table's
               name and schema.
        item: a dict object representing an item in the given table,
              which must conform to the expected schema.

    Returns:
        A dictionary response from AWS including an "Attributes" key.

    Raises:
        AWSClientError: If the AWS put fails.
        KeyError: If the response is missing an expected key.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the item does not conform to the expected schema.
    """
    if not isinstance(table, DynamoDBTable):
        raise TypeError(f"Table {table} is not a DynamoDBTable object.")
    if not isinstance(item, dict):
        raise TypeError(f"Item {item} is not a dict object.")
    table_name = table.value.name
    table_schema = table.value.schema
    if not validate_item_against_schema(table_schema, item):
        raise ValueError(f"Item {item} does not conform to the schema.")
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(table_name)
        response = table.put_item(Item=item)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return response


def validate_item_against_schema(schema, item):
    """Return whether or not the given item has the same format as the
    given schema.

    Args:
        schema: A dictionary mapping field name to expected value type.
        item: A dictionary mapping field name to value.

    Returns:
        A boolean representing whether or not the item matches the
        schema.

    Raises:
        TypeError: If either argument is not a dictionary.
    """
    if not isinstance(schema, dict):
        raise TypeError("Schema is not a dict object.")
    if not isinstance(item, dict):
        raise TypeError("Item is not a dict object.")
    if len(schema) != len(item):
        return False
    for key, value_type in schema.items():
        if key not in item:
            return False
        if not isinstance(item[key], value_type):
            return False
    return True
