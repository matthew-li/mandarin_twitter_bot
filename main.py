from aws_client import AWSClientError
from aws_client import get_tweets_on_date
from constants import AWSResource
from constants import DynamoDBTable
from constants import TWEETS_PER_DAY
from datetime import datetime
from datetime import timedelta
from mdbg_parser import MDBGParser
from settings import TWITTER_USER_USERNAME
from twitter_api_client import TwitterAPIClient
import boto3


def main():
    # Exit if the designated number of Tweets have already been posted today.
    today = datetime.today()
    tweets_today = get_tweets_on_date(today)
    if tweets_today["Count"] >= TWEETS_PER_DAY:
        return

    date_index = tweets_today["Count"]

    # Retrieve the next unprocessed word.
    dynamodb = boto3.resource(AWSResource.DYNAMO_DB)
    table = dynamodb.Table(DynamoDBTable.UNPROCESSED_WORDS)

    # This table is sorted by insertion timestamp, so get the first one.
    response = table.scan(Limit=1)
    items = response["Items"]
    entry = items[0]
    characters = entry["Characters"]
    pinyin = entry["Pinyin"]

    # Retrieve the word's definition.
    mdbg_parser = MDBGParser(characters, pinyin=pinyin)
    entry_found = mdbg_parser.run()
    if not entry_found:
        raise Exception(f"No entry found for {characters}.")
    print(f"Simplified: {mdbg_parser.simplified}")
    print(f"Pinyin: {mdbg_parser.pinyin}")
    print(f"Definitions: {mdbg_parser.definitions}")

    last_week = get_previous_tweet_details(
        today - timedelta(days=7), date_index=date_index)
    last_month = get_previous_tweet_details(
        today - timedelta(days=30), date_index=date_index)
    # Pick a random number of days, in range, to go back.
    days = 0
    random = get_previous_tweet_details(
        today - timedelta(days=days), date_index=date_index)
    body = format_tweet_body(mdbg_parser, last_week, last_month, random)

    twitter_client = TwitterAPIClient()
    twitter_client.post_tweet(body)

    # Create an entry in the Tweets table.


def get_previous_tweet_details(dt, date_index=None):
    """"""
    try:
        tweets = get_tweets_on_date(dt, tweet_idx=date_index)
    except AWSClientError as e:
        # Maybe just don't post for this one.
        return
    if tweets["Count"] == 0:
        tweet = None
    elif tweets["Count"] > 1:
        tweet = None
    else:
        tweet = tweets["Items"][0]

    word = tweet["Word"]
    tweet_id = tweet["TweetId"]

    tweet_exists = TwitterAPIClient().tweet_exists(str(tweet_id))
    if not tweet_exists:
        raise Exception()

    url = f"https://twitter.com/{TWITTER_USER_USERNAME}/statuses/{tweet_id}"
    return dict(tweet_id=tweet_id, word=word, url=url)


def format_tweet_body(mdbg_parser, last_week, last_month, random):
    content = (
        f"{mdbg_parser.simplified} ({mdbg_parser.pinyin}): "
        f"{', '.join(mdbg_parser.definitions)}"
    )
    if last_week is not None:
        content = content + "\n" + "Last Week: {}"
    if last_month is not None:
        content = content + "\n" + "Last Month: {}"
    if random is not None:
        content = content + "\n" + "Random: {}"

    # Validate that the tweet length does not exceed 280.
    # Each Chinese character counts as two characters.
    # Definitions may need to be truncated.

    return content


if __name__ == "__main__":
    main()
