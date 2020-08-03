from boto3.dynamodb.conditions import Key
from constants import AWSResource
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import datetime
from settings import DATE_FORMAT
import boto3
import botocore


class AWSClientError(Exception):
    """The base class for exceptions in this module."""
    pass


class DynamoDBSchema(object):

    tweets = {
        "TweetId": int,
        "Date": str,
        "DateIndex": int,
        "Word": str,
    }

    unprocessed_words = {
        "WordId": str,
        "Characters": str,
        "Pinyin": str,
    }


def get_tweets_on_date(dt, date_index=None):
    """Return the Tweets tweeted on the date represented by the given
    datetime object. Optionally also filters on the tweet's index on
    its date.

    Args:
        dt: A datetime object to be used to filter Tweets on their Date
            field.
        date_index: An integer used to filter Tweets on their DateIndex
                    field.

    Returns:
        A dictionary response from AWS including "Items" and "Count"
        keys.

    Raises:
        AWSClientError: If the AWS query fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the tweet index falls outside of the expected
                    range.
    """
    if not isinstance(dt, datetime):
        raise TypeError(f"Date {dt} is not a datetime object.")
    if date_index is not None:
        if not isinstance(date_index, int):
            raise TypeError(f"Date index {date_index} is not an integer.")
        if date_index < 0 or date_index >= TWEETS_PER_DAY:
            raise ValueError(f"Invalid date index {date_index}.")
    date = dt.strftime(DATE_FORMAT)
    try:
        dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
        table = dynamodb.Table(DynamoDBTable.TWEETS)
        kwargs = {
            "TableName": DynamoDBTable.TWEETS,
            "IndexName": "Date",
            "Select": "ALL_ATTRIBUTES",
            "Limit": TWEETS_PER_DAY,
            "KeyConditionExpression": Key("Date").eq(date),
        }
        if date_index is not None:
            kwargs["KeyConditionExpression"] &= Key("DateIndex").eq(date_index)
        response = table.query(**kwargs)
    except botocore.exceptions.ClientError as e:
        raise AWSClientError(
            f"Failed to retrieve response from AWS. Details: {e}")
    return response


def validate_document(document):
    """"""
    pass
