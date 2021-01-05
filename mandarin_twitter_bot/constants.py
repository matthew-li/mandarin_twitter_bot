from decimal import Decimal
from enum import Enum

"""This module contains constants referenced by the application."""


class AWSResource(object):
    """Names of AWS resources."""

    DYNAMO_DB = "dynamodb"


class DynamoDBSettings(object):
    """Names of keys to be stored in the DynamoDB Settings table."""

    EARLIEST_TWEET_DATE = "earliest_tweet_date"


class DynamoDBTableSchema(object):
    """A container for a DynamoDB table's name and expected schema."""

    def __init__(self, name, schema):
        self.name = name
        self.schema = schema


class DynamoDBTable(Enum):
    """DynamoDB tables, with name and schema information."""

    SETTINGS = DynamoDBTableSchema(
        name="Settings",
        schema={
            "Name": str,
            "Value": str,
        })

    TWEETS = DynamoDBTableSchema(
        name="Tweets",
        schema={
            "Id": str,
            "TweetId": str,
            "Date": str,
            "DateEntry": int,
            "Word": str,
        })

    UNPROCESSED_WORDS = DynamoDBTableSchema(
        name="UnprocessedWords",
        schema={
            "Id": str,
            "Characters": str,
            "Pinyin": str,
            "InsertionTimestamp": Decimal,
        })


class TwitterBotExitCodes(Enum):
    """Exit codes for the possible outcomes of the main method."""

    OK = 0
    UNHANDLED = 1
    MAX_TWEETS_EXCEEDED = 2
    NO_WORDS_LEFT = 3
    BAD_DICTIONARY_RESPONSE = 4
    NO_DICTIONARY_ENTRY = 5
    TWEET_FAILED = 6
    DB_FAILED = 7


# The maximum number of characters allowed in a Tweet.
TWEET_MAX_CHARS = 280
# The length to which URLs are modified during Tweet creation.
TWEET_URL_LENGTH = 23
# The number of Tweets the application should post per day.
TWEETS_PER_DAY = 3
