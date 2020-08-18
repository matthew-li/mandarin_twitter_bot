from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key
from constants import AWSResource
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import datetime
from settings import DATE_FORMAT
import boto3
import botocore
import uuid


class AWSClientError(Exception):
    """The base class for exceptions in this module."""
    pass


class DynamoDBSchema(object):
    """DynamoDB tables and their expected formats."""

    tweets = {
        "Id": str,
        "TweetId": str,
        "Date": str,
        "DateEntry": int,
        "Word": str,
        "CreationTimestamp": int,
    }

    unprocessed_words = {
        "Id": str,
        "Characters": str,
        "Pinyin": str,
        "InsertionTimestamp": int,
    }


def batch_put_unprocessed_words(unprocessed_words):
    """Store the unprocessed words represented by the given list of
    dictionaries in a batch write after validating that each conforms to
    the expected schema. Return the response.

    Args:
        unprocessed_words: a list of dict objects representing
                           UnprocessedWords, each of which must conform
                           to the expected schema.

    Returns:
        A dictionary response with key "success" mapping to True.

    Raises:
        AWSClientError: If the AWS put fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If any UnprocessedWord does not conform to the
                    expected schema.
    """
    if not isinstance(unprocessed_words, list):
        raise TypeError(
            f"UnprocessedWords {unprocessed_words} is not a list object.")
    schema = DynamoDBSchema.unprocessed_words
    for unprocessed_word in unprocessed_words:
        if not isinstance(unprocessed_word, dict):
            raise TypeError(
                f"UnprocessedWord {unprocessed_word} is not a dict object.")
        if not validate_item_against_schema(schema, unprocessed_word):
            raise ValueError(
                f"UnprocessedWord {unprocessed_word} does not conform to the "
                f"schema.")
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(DynamoDBTable.UNPROCESSED_WORDS)
        with table.batch_writer() as batch:
            for unprocessed_word in unprocessed_words:
                batch.put_item(Item=unprocessed_word)
    except boto3.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return dict(success=True)


def get_random_previous_tweet():
    """Return a random previously-tweeted Tweet.

    Args:
        None.

    Returns:
        A dictionary response from AWS including "Items" and "Count"
        keys.

    Raises:
        AWSClientError: If the AWS query fails.
    """
    random_id = str(uuid.uuid4())
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(DynamoDBTable.TWEETS)
        # Find a record with UUID less than or equal to the given random UUID.
        kwargs = {
            "TableName": DynamoDBTable.TWEETS,
            "Select": "ALL_ATTRIBUTES",
            "KeyConditionExpression": Key("Id").le(random_id),
        }
        response = table.query(**kwargs)
        # If the UUID was less than the smallest stored, find a greater one.
        if response["Count"] == 0:
            kwargs["KeyConditionExpression"] = Key("Id").gt(random_id)
            response = table.query(**kwargs)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return response


def get_tweets_on_date(dt, date_entry=None):
    """Return the Tweets tweeted on the date represented by the given
    datetime object. Optionally also filter on what number entry the
    tweet was on its date.

    Args:
        dt: A datetime object to be used to filter Tweets on their Date
            field.
        date_entry: An integer used to filter Tweets on their DateEntry
                    field.

    Returns:
        A dictionary response from AWS including "Items" and "Count"
        keys.

    Raises:
        AWSClientError: If the AWS query fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the tweet entry falls outside of the expected
                    range.
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Date {dt} is not a datetime object.")
    if date_entry is not None:
        if not isinstance(date_entry, int):
            raise TypeError(f"Date entry {date_entry} is not an integer.")
        if date_entry < 0 or date_entry >= TWEETS_PER_DAY:
            raise ValueError(f"Invalid date entry {date_entry}.")
    date = dt.strftime(DATE_FORMAT)
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(DynamoDBTable.TWEETS)
        kwargs = {
            "TableName": DynamoDBTable.TWEETS,
            "IndexName": "DateIndex",
            "Select": "ALL_ATTRIBUTES",
            "KeyConditionExpression": Key("Date").eq(date)
        }
        if date_entry is not None:
            kwargs["FilterExpression"] &= Attr("DateEntry").eq(date_entry)
        response = table.query(**kwargs)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return response


def put_tweet(tweet):
    """Store the Tweet represented by the given dictionary after
    validating that it conforms to the expected schema. Return the
    response.

    Args:
        tweet: a dict object representing a Tweet, which must conform to
               the expected schema.

    Returns:
        A dictionary response from AWS including an "Attributes" key.

    Raises:
        AWSClientError: If the AWS put fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the Tweet does not conform to the expected
                    schema.
    """
    if not isinstance(tweet, dict):
        raise TypeError(f"Tweet {tweet} is not a dict object.")
    schema = DynamoDBSchema.tweets
    if not validate_item_against_schema(schema, tweet):
        raise ValueError(f"Tweet {tweet} does not conform to the schema.")
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(DynamoDBTable.TWEETS)
        response = table.put_item(Item=tweet)
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
