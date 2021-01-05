from boto3.dynamodb.conditions import Key
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import date
from datetime import datetime
from decimal import Decimal
from settings import AWS_DYNAMODB_ENDPOINT_URL
from settings import DATE_FORMAT
import boto3
import botocore

"""This module contains methods that interface with resources stored in
Amazon Web Services."""


class AWSClientError(Exception):
    """The base class for exceptions in this module."""

    def __init__(self, aws_error, message=""):
        if not message.strip():
            message = "Failed to retrieve response from AWS. Details: "
        message = message + str(aws_error)
        super().__init__(message)


def batch_put_items(table, items):
    """Stores the items represented by the given list of dictionaries in
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
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        table = dynamodb.Table(table_name)
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(e.response["Error"])


def get_and_delete_unprocessed_word():
    """Returns an UnprocessedWord after validating that it conforms to
    the expected schema. Deletes it from the table.

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
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
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
        raise AWSClientError(e.response["Error"])
    if not validate_item_against_schema(table_schema, item):
        raise ValueError(f"Item {item} does not conform to the schema.")
    return item


def get_earliest_tweet_date():
    """Returns the date of the earliest Tweet stored. If this date has
    been previously stored, retrieves it from the Settings table.
    Otherwise, returns None.

    Args:
        None.

    Returns:
        A string conforming to settings.DATE_FORMAT or None.

    Raises:
        AWSClientError: If the AWS query fails.
    """
    try:
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        table_name = DynamoDBTable.SETTINGS.value.name
        table = dynamodb.Table(table_name)
        kwargs = {
            "TableName": table_name,
            "Select": "ALL_ATTRIBUTES",
            "KeyConditionExpression": Key("Name").eq(
                DynamoDBSettings.EARLIEST_TWEET_DATE)
        }
        response = table.query(**kwargs)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(e.response["Error"])
    items = response["Items"]
    if items:
        entry = items[0]
        return entry["Value"]
    return None


def get_tweets_on_date(d, date_entry=None):
    """Returns the Tweets tweeted on the date represented by the given
    date object. Optionally also filters on what number entry the Tweet
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
        ValueError: If the Tweet entry falls outside of the expected
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
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
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
            # Number types are stored in DynamoDB as Decimals.
            if isinstance(item["DateEntry"], Decimal):
                item["DateEntry"] = int(item["DateEntry"])
            tweets.append(item)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(e.response["Error"])
    return tweets


def put_item(table, item):
    """Stores the item represented by the given dictionary in the given
    table after validating that it conforms to the expected schema.
    Returns the response.

    Args:
        table: an instance of DynamoDBTable, which contains the table's
               name and schema.
        item: a dict object representing an item in the given table,
              which must conform to the expected schema.

    Returns:
        A dictionary response from AWS including a "ResponseMetadata"
        key.

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
        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        table = dynamodb.Table(table_name)
        response = table.put_item(Item=item)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(e.response["Error"])
    return response


def set_earliest_tweet_date(date_str):
    """Sets the earliest tweet date in the Settings table.

    Args:
        date_str: A string conforming to settings.DATE_FORMAT

    Returns:
        None

    Raises:
        AWSClientError: If the AWS query fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the date string does not conform to the expected
                    format.
    """
    if not isinstance(date_str, str):
        raise TypeError(f"Date {date_str} is not a string object.")
    try:
        datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        raise ValueError(
            f"Date {date_str} does not conform to the expected format "
            f"{DATE_FORMAT}.")
    item = {
        "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
        "Value": date_str,
    }
    put_item(DynamoDBTable.SETTINGS, item)


def validate_item_against_schema(schema, item):
    """Returns whether or not the given item has the same format as the
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
