from aws_client import AWSClientError
from aws_client import get_random_previous_tweet
from aws_client import get_tweets_on_date
from collections import namedtuple
from constants import AWSResource
from constants import DynamoDBTable
from constants import TWEET_MAX_CHARS
from constants import TWEET_URL_LENGTH
from constants import TWEETS_PER_DAY
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
from mdbg_parser import MDBGParser
from settings import DATE_FORMAT
from settings import TWITTER_USER_USERNAME
from twitter_api_client import TwitterAPIClient
import boto3
import uuid

""""""


def main():
    """

    """
    # Exit if the designated number of Tweets have already been posted today.
    today = datetime.today()
    tweets_today = get_tweets_on_date(today)
    if tweets_today["Count"] >= TWEETS_PER_DAY:
        return

    date_entry = tweets_today["Count"]

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

    # Retrieve previous Tweets.
    last_week = get_previous_tweet_details(
        today - timedelta(days=7), date_entry=date_entry)
    last_month = get_previous_tweet_details(
        today - timedelta(days=30), date_entry=date_entry)
    random = get_random_previous_tweet()

    # Construct the body of the Tweet.
    body = generate_tweet_body(mdbg_parser, last_week, last_month, random)

    # Post the Tweet.
    twitter_client = TwitterAPIClient()
    post_response = twitter_client.post_tweet(body)

    # Check the response.
    if response.status_code != HTTPStatus.OK:
        return

    json = post_response.json()
    tweet_id_str = json["id_str"]
    created_at = json["created_at"]                                            # "Wed Oct 10 20:19:24 +0000 2018"
    creation_timestamp = 0

    # Create an entry in the Tweets table.
    table = dynamodb.Table(DynamoDBTable.TWEETS)
    response = table.put_item(
        Item={
            "Id": str(uuid.uuid4()),
            "TweetId": tweet_id_str,
            "Date": today.strftime(DATE_FORMAT),
            "DateEntry": date_entry,
            "Word": mdbg_parser.simplified,
            "CreationTimestamp": creation_timestamp,
        })

    # Check the response.


def get_previous_tweet_details(dt, date_entry=None):
    """"""
    try:
        tweets = get_tweets_on_date(dt, date_entry=date_entry)
    except AWSClientError as e:
        return dict()
    if tweets["Count"] == 0:
        tweet = None
    elif tweets["Count"] > 1:
        tweet = None
    else:
        tweet = tweets["Items"][0]

    if not tweet:
        return dict()

    word = tweet["Word"]
    tweet_id = tweet["TweetId"]

    tweet_exists = TwitterAPIClient().tweet_exists(str(tweet_id))
    if not tweet_exists:
        raise Exception()

    url = f"https://twitter.com/{TWITTER_USER_USERNAME}/statuses/{tweet_id}"
    return dict(tweet_id=tweet_id, word=word, url=url)


def generate_tweet_body(mdbg_parser, last_week={}, last_month={}, random={}):
    """Return the formatted body of a new Tweet, given the current
    and previous entries.

    Args:
        mdbg_parser: An instance of MDBGParser, which contains the
                     current word, pinyin, and definitions.
        last_week: A dictionary representing the Tweet from seven days
                   ago, with "word" and "url" keys.
        last_month: A dictionary representing the Tweet from thirty days
                    ago, with "word" and "url" keys.
        random: A dictionary representing the Tweet from a random number
                of days ago, with "word" and "url" keys.

    Returns:
        A string representing the body of the new Tweet.

    Raises:
        Exception.
    """
    TweetEntry = namedtuple("TweetEntry", "entry char_count")
    tweet_entries = dict()

    # Compute the previous entries.
    remaining_chars = TWEET_MAX_CHARS
    previous_tweets = (
        ("Last Week", last_week),
        ("Last Month", last_month),
        ("Random", random),
    )
    for label, tweet in previous_tweets:
        if not tweet:
            continue
        if "word" not in tweet or "url" not in tweet:
            continue
        entry = f"\n{label}: {tweet['word']} ({tweet['url']})"
        char_count = (len(entry) +
                      len(tweet["word"]) -
                      len(tweet["url"]) +
                      TWEET_URL_LENGTH)

        if remaining_chars - char_count <= 0:
            continue
        remaining_chars = remaining_chars - char_count
        tweet_entries[label] = TweetEntry(entry=entry, char_count=char_count)

    # Compute the current entry.
    entry = f"{mdbg_parser.simplified} ({mdbg_parser.pinyin}): "
    char_count = len(entry) + len(mdbg_parser.simplified)
    filtered_definitions = []
    for _, definition in enumerate(mdbg_parser.definitions):
        updated_count = char_count + len("; ".join(filtered_definitions))
        if filtered_definitions:
            # Account for prepending "; ".
            updated_count = updated_count + 2
        if remaining_chars - (updated_count + len(definition)) < 0:
            continue
        filtered_definitions.append(definition)
    if filtered_definitions:
        addition = "; ".join(filtered_definitions)
    else:
        addition = "Not available"
    entry = entry + addition
    char_count = char_count + len(addition)
    entry = entry + "\n"
    char_count = char_count + 1
    tweet_entries["Now"] = TweetEntry(entry=entry, char_count=char_count)
    remaining_chars = remaining_chars - char_count

    # Remove previous entries if the character count has been exceeded.
    for label in ("Random", "Last Month", "Last Week"):
        if remaining_chars >= 0:
            break
        try:
            tweet_entry = tweet_entries.pop(label)
        except KeyError:
            continue
        remaining_chars = remaining_chars - tweet_entry.char_count

    # Construct the Tweet.
    body = tweet_entries["Now"].entry
    for label in ("Last Week", "Last Month", "Random"):
        if label in tweet_entries:
            body = body + tweet_entries[label].entry
    return body


if __name__ == "__main__":
    pass
