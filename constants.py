from decimal import Decimal
from enum import Enum


class AWSResource(object):
    """"""
    DYNAMO_DB = "dynamodb"


class DynamoDBSettings(object):
    """"""
    EARLIEST_TWEET_DATE = "earliest_tweet_date"


class DynamoDBTableSchema(object):
    """"""

    def __init__(self, name, schema):
        self.name = name
        self.schema = schema


class DynamoDBTable(Enum):
    """"""
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
            "DateEntry": Decimal,
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


TWEET_MAX_CHARS = 280
TWEET_URL_LENGTH = 23
TWEETS_PER_DAY = 3
