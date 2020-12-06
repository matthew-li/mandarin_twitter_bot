from aws_client import AWSClientError
from aws_client import get_and_delete_unprocessed_word
from aws_client import get_earliest_tweet_date
from aws_client import get_tweets_on_date
from aws_client import put_item
from aws_client import set_earliest_tweet_date
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
from mdbg_parser import MDBGError
from mdbg_parser import MDBGParser
from settings import DATE_FORMAT
from settings import TWITTER_USER_USERNAME
from twitter_api_client import TwitterAPIClient
from utils import random_dates_in_range
from utils import tweet_url
import sys
import traceback
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
        sys.stderr.write(
            f"The maximum number of Tweets ({TWEETS_PER_DAY}) for today has "
            f"been exceeded. Exiting.")
        return
    date_entry = num_tweets_today

    # Retrieve the next unprocessed word and delete it from the table.
    unprocessed_word = get_and_delete_unprocessed_word()
    if not unprocessed_word:
        sys.stderr.write("There are no words left to process. Exiting.")
        return
    characters = unprocessed_word["Characters"]
    pinyin = unprocessed_word["Pinyin"]

    # Retrieve the word's definition.
    mdbg_parser = MDBGParser(characters, pinyin=pinyin)
    try:
        entry_found = mdbg_parser.run()
    except MDBGError:
        sys.stderr.write(
            f"Failed to retrieve a valid response from the dictionary. "
            f"Exiting. Details:\n")
        traceback.print_exc(file=sys.stderr)
        return
    if not entry_found:
        sys.stderr.write(
            f"No dictionary entry was found for {characters}. Exiting.")
        return

    # Retrieve previous Tweets.
    previous_tweets = get_previous_tweets(date_entry)

    # Construct the body of the Tweet.
    body = generate_tweet_body(mdbg_parser, previous_tweets)

    # Post the Tweet.
    tweet_id_str = TwitterAPIClient().post_tweet(body)
    if tweet_id_str is None:
        sys.stderr.write(
            f"Failed to create a Tweet with body '{body.strip()}'. Exiting.")
        return

    # Create an entry in the Tweets table.
    tweet = {
        "Id": str(uuid.uuid4()),
        "TweetId": tweet_id_str,
        "Date": today.strftime(DATE_FORMAT),
        "DateEntry": date_entry,
        "Word": mdbg_parser.simplified,
    }
    try:
        put_item(DynamoDBTable.TWEETS, tweet)
    except AWSClientError as e:
        sys.stderr.write(
            f"Failed to save posted Tweet. Exiting. Details:\n{e}")
        traceback.print_exc(file=sys.stderr)
        return

    # If no earliest Tweet date has been recorded, store this one.
    if get_earliest_tweet_date() is None:
        try:
            set_earliest_tweet_date(tweet["Date"])
        except AWSClientError as e:
            sys.stderr.write(
                f"Failed to save {DynamoDBSettings.EARLIEST_TWEET_DATE} "
                f"setting. Exiting. Details:\n{e}")
            return

    # Output a success message.
    message = (
        f"Posted {tweet['Word']} with Tweet ID {tweet['TweetId']} and "
        f"internal ID {tweet['Id']} as entry {tweet['DateEntry']} on date "
        f"{tweet['Date']}.")
    sys.stdout.write(message)


def generate_tweet_body(mdbg_parser, previous_tweets):
    """Return the formatted body of a new Tweet, given the current
    and previous entries.

    Twitter counts each Chinese character twice against the Tweet body
    limit. All URLs are modified to have length TWEET_URL_LENGTH.

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
        tweet_entries[label] = TweetEntry(entry=entry, char_count=char_count)

    # At minimum, the word and pinyin are required.
    entry = f"{mdbg_parser.simplified} ({mdbg_parser.pinyin})"
    char_count = len(entry) + len(mdbg_parser.simplified)
    if char_count > TWEET_MAX_CHARS:
        raise ValueError(
            f"Entry {entry} exceeds {TWEET_MAX_CHARS} characters.")
    tweet_entries["Now"] = TweetEntry(entry=entry, char_count=char_count)

    # Add the first definition that does not cause the character count to be
    # exceeded. If all of them do, include no definition.
    entry = f"{tweet_entries['Now'].entry}: "
    char_count = tweet_entries["Now"].char_count + 2
    definition_index = 0
    while definition_index < len(mdbg_parser.definitions):
        definition = mdbg_parser.definitions[definition_index]
        if char_count + len(definition) <= TWEET_MAX_CHARS:
            break
        definition_index = definition_index + 1
    if definition_index != len(mdbg_parser.definitions):
        addition = mdbg_parser.definitions[definition_index]
        entry = entry + addition
        char_count = char_count + len(addition)
    else:
        entry = entry[:-2]
        char_count = char_count - 2
    tweet_entries["Now"] = TweetEntry(entry=entry, char_count=char_count)

    # Add a newline after the current entry.
    entry = tweet_entries["Now"].entry
    char_count = tweet_entries["Now"].char_count
    if char_count + 1 >= TWEET_MAX_CHARS:
        return entry
    else:
        entry = f"{entry}\n"
        char_count = char_count + 1
        tweet_entries["Now"] = TweetEntry(entry=entry, char_count=char_count)

    # Compute the previous entries.
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
        tweet_entries[label] = TweetEntry(entry=entry, char_count=char_count)

    # Include as many previous entries as possible.
    included_entries = []
    now = tweet_entries["Now"]
    remaining_chars = TWEET_MAX_CHARS - now.char_count
    included_entries.append(now.entry)

    labels = ["Last Week", "Last Month", "Random"]
    i = 0
    while i < len(labels) and remaining_chars >= 0:
        label = labels[i]
        if label in tweet_entries:
            previous = tweet_entries[label]
            if remaining_chars - previous.char_count >= 0:
                included_entries.append(previous.entry)
                remaining_chars = remaining_chars - previous.char_count
        i = i + 1

    # Include as many definitions for the current entry as possible.
    entry = tweet_entries['Now'].entry
    i = 0
    while i < len(mdbg_parser.definitions):
        if i != definition_index:
            definition = mdbg_parser.definitions[i]
            addition_char_count = len(definition) + 2
            if remaining_chars - addition_char_count >= 0:
                entry = f"{entry[:-1]}; {definition}\n"
                remaining_chars = remaining_chars - addition_char_count
        i = i + 1
    included_entries[0] = entry

    return "".join(included_entries).strip()


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

    Raises:
        AWSClientError: If any AWS query fails.
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If the Tweet entry falls outside of the expected
                    range.
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
            # TODO: Log
            continue
        if not tweets:
            # TODO: Log
            continue
        if len(tweets) > 1:
            # TODO: Log a warning, but proceed
            pass
        tweet = tweets[0]
        if not validate_item_against_schema(table_schema, tweet):
            # TODO: Log
            continue
        tweet_id = tweet["TweetId"]
        if not twitter_client.tweet_exists(tweet_id):
            # TODO: Log
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
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If one or more inputs is outside of its expected
                    range.
    """
    min_date = get_earliest_tweet_date()
    if min_date is None:
        return []
    start = datetime.strptime(min_date, DATE_FORMAT).date()
    end = date.today()
    if start == end:
        return []
    random_dates = random_dates_in_range(start, end, num_tries)
    for random_date in random_dates:
        tweets = get_tweets_on_date(random_date, date_entry=date_entry)
        if tweets:
            return tweets
    return []


if __name__ == "__main__":
    main()
