from aws_client import AWSClientError
from aws_client import get_and_delete_unprocessed_word
from aws_client import get_earliest_tweet_date
from aws_client import get_tweets_on_date
from aws_client import put_item
from aws_client import validate_item_against_schema
from collections import namedtuple
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEET_MAX_CHARS
from constants import TWEET_URL_LENGTH
from constants import TWEETS_PER_DAY
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from mdbg_parser import MDBGParser
from settings import DATE_FORMAT
from settings import TWITTER_USER_USERNAME
from twitter_api_client import TwitterAPIClient
from utils import random_dates_in_range
from utils import tweet_url
import uuid

"""This module contains the methods needed to post a Tweet containing a
word, details about that word, and URLs to previously posted Tweets."""


def main():
    """This method performs creates a new Tweet.

    In particular, it performs the following:
        1. Pop an unprocessed word from DynamoDB.
        2. Retrieve the word's definition from the MDBG dictionary.
        3. Retrieve information about previously posted Tweets from
           DynamoDB.
        4. Construct and post a new Tweet.
        5. Store information about the new Tweet in DynamoDB.
    """
    # Exit if the designated number of Tweets have already been posted today.
    today = date.today()
    num_tweets_today = len(get_tweets_on_date(today))
    if num_tweets_today >= TWEETS_PER_DAY:
        # Log
        return
    date_entry = num_tweets_today

    # Retrieve the next unprocessed word and delete it from the table.
    unprocessed_word = get_and_delete_unprocessed_word()
    if not unprocessed_word:
        # Log
        return
    characters = unprocessed_word["Characters"]
    pinyin = unprocessed_word["Pinyin"]

    # Retrieve the word's definition.
    mdbg_parser = MDBGParser(characters, pinyin=pinyin)
    entry_found = mdbg_parser.run()
    if not entry_found:
        raise Exception(f"No entry found for {characters}.")

    # Retrieve previous Tweets.
    previous_tweets = get_previous_tweets(date_entry)

    # Construct the body of the Tweet.
    body = generate_tweet_body(mdbg_parser, previous_tweets)

    # Post the Tweet.
    tweet_id_str = TwitterAPIClient().post_tweet(body)
    if tweet_id_str is None:
        raise Exception(f"Failed to create Tweet with body {body}.")

    # Create an entry in the Tweets table.
    tweet = {
        "Id": str(uuid.uuid4()),
        "TweetId": tweet_id_str,
        "Date": today.strftime(DATE_FORMAT),
        "DateEntry": Decimal(str(date_entry)),
        "Word": mdbg_parser.simplified,
    }
    try:
        put_item(DynamoDBTable.TWEETS, tweet)
    except AWSClientError as e:
        raise e

    # If no earliest Tweet date has been recorded, store this one.
    if get_earliest_tweet_date() is None:
        setting = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": tweet["Date"],
        }
        try:
            put_item(DynamoDBTable.SETTINGS, setting)
        except AWSClientError as e:
            # Log a warning, but proceed
            pass


def generate_tweet_body(mdbg_parser, previous_tweets):
    """Return the formatted body of a new Tweet, given the current
    and previous entries.

    Args:
        mdbg_parser: An instance of MDBGParser, which contains the
                     current word, pinyin, and definitions.
        previous_tweets: A namedtuple with name PreviousTweets and
                         fields with names "last_week", "last_month",
                         and "random", where each name points to a
                         dictionary containing the Tweet's Twitter ID,
                         the word associated with the Tweet, and the URL
                         to the Tweet.

    Returns:
        A string representing the body of the new Tweet.

    Raises:
        Exception, if any errors occur.
    """
    TweetEntry = namedtuple("TweetEntry", "entry char_count")
    tweet_entries = dict()

    # Compute the previous entries.
    remaining_chars = TWEET_MAX_CHARS
    previous_tweets_and_labels = (
        ("Last Week", previous_tweets.last_week),
        ("Last Month", previous_tweets.last_month),
        ("Random", previous_tweets.random),
    )
    for label, tweet in previous_tweets_and_labels:
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


def get_previous_tweets(date_entry):
    """Return details about previous Tweets. Namely, retrieve details
    about the date_entry-th Tweets from 7 days ago, 30 days ago, and a
    random number of days ago.

    If a given Tweet does not exist, its corresponding entry in the
    output will be empty.

    Args:
        date_entry: An integer representing the number of Tweets tweeted
                    before the desired one on the date it was tweeted.

    Returns:
        A namedtuple with name PreviousTweets and fields with names
        "last_week", "last_month", and "random", where each name points
        to a dictionary containing the Tweet's Twitter ID, the word
        associated with the Tweet, and the URL to the Tweet.
    """
    today = date.today()
    tweets_by_date = {
        "last_week": get_tweets_on_date(
            today - timedelta(days=7), date_entry=date_entry),
        "last_month": get_tweets_on_date(
            today - timedelta(days=30), date_entry=date_entry),
        "random": get_tweets_on_random_date(date_entry=date_entry),
    }
    twitter_client = TwitterAPIClient()
    table_schema = DynamoDBTable.TWEETS.value.schema

    for date_key in ("last_week", "last_month", "random"):
        tweets = tweets_by_date[date_key]
        tweets_by_date[date_key] = dict()
        if not isinstance(tweets, list):
            # Log
            continue
        if not tweets:
            # Log
            continue
        if len(tweets) > 1:
            # Log a warning, but proceed
            pass
        tweet = tweets[0]
        if not validate_item_against_schema(table_schema, tweet):
            # Log
            continue
        tweet_id = tweet["TweetId"]
        if not twitter_client.tweet_exists(tweet_id):
            # Log
            continue
        word = tweet["Word"]
        url = tweet_url(TWITTER_USER_USERNAME, tweet_id)
        tweets_by_date[date_key] = dict(tweet_id=tweet_id, word=word, url=url)

    PreviousTweets = namedtuple(
        "PreviousTweets", "last_week last_month random")
    return PreviousTweets(
        last_week=tweets_by_date["last_week"],
        last_month=tweets_by_date["last_month"],
        random=tweets_by_date["random"])


def get_tweets_on_random_date(date_entry=None, num_tries=5):
    """Return Tweets from a random previous date. Optionally also filter
    on what number entry the Tweet was on its date. Make at most
    num_tries attempts.

    Args:
        date_entry: An integer used to filter Tweets on their DateEntry
            field.
        num_tries: The number of attempts to make to retrieve a Tweet.

    Returns:
        A list of dictionaries representing entries in the Tweets table.

    Raises:
        AWSClientError: If any AWS query fails.
        TypeError: Raised by the subroutine for computing random dates.
        ValueError: Raised by the subroutine for computing random dates.
    """
    min_date = get_earliest_tweet_date()
    if min_date is None:
        return None
    start = datetime.strptime(min_date, DATE_FORMAT).date()
    end = date.today()
    random_dates = random_dates_in_range(start, end, num_tries)
    for random_date in random_dates:
        tweets = get_tweets_on_date(random_date, date_entry=date_entry)
        if tweets:
            return tweets
    return []


if __name__ == "__main__":
    main()
