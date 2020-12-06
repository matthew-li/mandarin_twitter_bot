from aws_client import AWSClientError
from aws_client import get_and_delete_unprocessed_word
from aws_client import get_earliest_tweet_date
from aws_client import get_tweets_on_date
from aws_client import batch_put_items
from aws_client import put_item
from aws_client import set_earliest_tweet_date
from collections import namedtuple
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEET_MAX_CHARS
from constants import TWEET_URL_LENGTH
from constants import TWEETS_PER_DAY
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date
from datetime import timedelta
from io import StringIO
from main import generate_tweet_body
from main import get_previous_tweets
from main import get_tweets_on_random_date
from main import main as run_twitter_bot
from mdbg_parser import MDBGError
from mdbg_parser import MDBGParser
from settings import AWS_DYNAMODB_ENDPOINT_URL
from settings import DATE_FORMAT
from settings import TWITTER_USER_USERNAME
from tests.test_aws_client import TestDynamoDBMixin
from twitter_api_client import TwitterAPIClient
from unittest import TestCase
from unittest.mock import patch
from utils import tweet_url
from utils import utc_seconds_since_the_epoch
import boto3
import re
import uuid

"""A test module for the main functionality of the application."""


class TestTwitterBotErrors(TestDynamoDBMixin):
    """A class for testing that the main method of the main application
    handles errors as expected."""

    def setUp(self):
        super().setUp()
        self.twitter_api = TwitterAPIClient()
        self.created_tweets = set()
        self.addCleanup(self.delete_created_tweets)

    def delete_created_tweets(self):
        """Delete created Tweets from Twitter."""
        for tweet_id in self.created_tweets:
            self.twitter_api.delete_tweet(tweet_id)
            self.assertFalse(self.twitter_api.tweet_exists(tweet_id))

    def test_too_many_tweets_today(self):
        """Test that, if the maximum number of Tweets have already been
        posted today, the application exits."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "再见",
            "Pinyin": "zài jiàn",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        table = DynamoDBTable.TWEETS
        today = date.today()
        words = iter(["我", "你", "好"])
        for i in range(TWEETS_PER_DAY):
            tweet = {
                "Id": str(uuid.uuid4()),
                "TweetId": str(i),
                "Date": today.strftime(DATE_FORMAT),
                "DateEntry": i,
                "Word": next(words),
            }
            put_item(table, tweet)
            key = {
                "Id": tweet["Id"],
                "Date": tweet["Date"],
            }
            self.created_items[table.value.name].append(key)

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()

        message = (
            "The maximum number of Tweets (3) for today has been exceeded. "
            "Exiting.")
        self.assertEqual(f.getvalue(), message)

        # The UnprocessedWord should not have been processed; it should still
        # be in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, item)

        # No new Tweet should have been created.
        self.assertFalse(
            self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME))

        # There should still only be TWEETS_PER_DAY Tweets tweeted today.
        self.assertEqual(len(get_tweets_on_date(today)), TWEETS_PER_DAY)

        # Because the earlier tweets were not created via the main method, the
        # EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    def test_no_unprocessed_words_left(self):
        """Test that, if there are no words left to process, the
        application exits."""
        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()

        message = "There are no words left to process. Exiting."
        self.assertEqual(f.getvalue(), message)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # No new Tweet should have been created.
        self.assertFalse(
            self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME))

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    @patch.object(MDBGParser, "run")
    def test_dictionary_parser_error_caught(self, mock_run):
        """Test that, if the dictionary parser raises an error, it is
        caught, the stack trace is outputted, and the application exits.
        """
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "12345",
            "Pinyin": "12345",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        # Patch the method for running the dictionary parser to raise an error.
        def raise_mdbg_error():
            raise MDBGError("This exception is expected.")
        mock_run.side_effect = raise_mdbg_error

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()
        mock_run.assert_called()

        output = f.getvalue()
        message = (
            "Failed to retrieve a valid response from the dictionary. "
            "Exiting. Details:\n")
        self.assertTrue(output.startswith(message))
        self.assertIn("Traceback", output)
        self.assertIn("This exception is expected.", output)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # No new Tweet should have been created.
        self.assertFalse(
            self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME))

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    def test_word_not_in_dictionary(self):
        """Test that, if the word is not found in the MDBG dictionary,
        the application exits."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "12345",
            "Pinyin": "12345",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()

        message = (
            f"No dictionary entry was found for {item['Pinyin']}. Exiting.")
        self.assertEqual(f.getvalue(), message)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # No new Tweet should have been created.
        self.assertFalse(
            self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME))

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    @patch.object(TwitterAPIClient, "post_tweet")
    def test_twitter_post_fails(self, mock_post_tweet):
        """Test that, if the POST request to Twitter fails, the
        application exits."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "再见",
            "Pinyin": "zài jiàn",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        # Patch the method for posting a Tweet to return None.
        mock_post_tweet.return_value = None

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()
        mock_post_tweet.assert_called()

        output = f.getvalue()
        message = "Failed to create a Tweet with body '再见"
        self.assertTrue(output.startswith(message))
        self.assertTrue(output.endswith("'. Exiting."))

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # No new Tweet should have been created.
        self.assertFalse(
            self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME))

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    @patch("main.put_item")
    def test_aws_tweet_put_fails(self, mock_put_item):
        """Test that, if the request to put the Tweet in DynamoDB fails,
        the application exits."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "再见",
            "Pinyin": "zài jiàn",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        # Patch the method for putting an item in DynamoDB to raise an
        # AWSClientError.
        def raise_aws_client_error(table, item):
            raise AWSClientError("This exception is expected.")
        mock_put_item.side_effect = raise_aws_client_error

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()
        mock_put_item.assert_called()

        output = f.getvalue()
        message = "Failed to save posted Tweet. Exiting. Details:\n"
        self.assertTrue(output.startswith(message))
        self.assertIn("This exception is expected.", output)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)
        tweet_id_str = created_tweets[0]["id_str"]
        self.created_tweets.add(tweet_id_str)

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    @patch("main.put_item")
    def test_aws_setting_put_fails(self, mock_put_item):
        """Test that, if the request to put the setting for the earliest
        Tweet date in DynamoDB fails, the application exits."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "再见",
            "Pinyin": "zài jiàn",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        # Patch the method for putting an item in DynamoDB to raise an
        # AWSClientError if the table is the "Settings" table.
        def raise_aws_client_error_conditionally(table, item):
            if table.value.name == DynamoDBTable.SETTINGS.value.name:
                raise AWSClientError("This exception is expected.")
            return put_item(table, item)
        mock_put_item.side_effect = raise_aws_client_error_conditionally

        f = StringIO()
        with redirect_stderr(f):
            run_twitter_bot()
        mock_put_item.assert_called()

        output = f.getvalue()
        message = (
            "Failed to save earliest_tweet_date setting. Exiting. Details:\n")
        self.assertTrue(output.startswith(message))
        self.assertIn("This exception is expected.", output)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)
        tweet_id_str = created_tweets[0]["id_str"]
        self.created_tweets.add(tweet_id_str)

        # A record of the Tweet should have been created.
        today = date.today()
        tweets = get_tweets_on_date(today)
        self.assertEqual(len(tweets), 1)
        tweet = tweets[0]
        self.assertEqual(tweet["TweetId"], tweet_id_str)
        self.assertEqual(tweet["Date"], str(today))
        self.assertEqual(tweet["DateEntry"], 0)
        self.assertEqual(tweet["Word"], item["Characters"])
        table = DynamoDBTable.TWEETS
        self.created_items[table.value.name].append({
            "Id": tweet["Id"],
            "Date": tweet["Date"],
        })

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())


class TestTwitterBot(TestDynamoDBMixin):
    """A class for testing the main method of the main application."""

    def setUp(self):
        super().setUp()
        self.username = TWITTER_USER_USERNAME
        self.twitter_api = TwitterAPIClient()
        self.created_tweets = set()
        self.previous_tweets = namedtuple(
            "PreviousTweets", "last_week last_month random")
        self.addCleanup(self.delete_created_tweets)

    def delete_created_tweets(self):
        """Delete created Tweets from Twitter."""
        for tweet_id in self.created_tweets:
            self.twitter_api.delete_tweet(tweet_id)
            self.assertFalse(self.twitter_api.tweet_exists(tweet_id))

    def assert_success_message(self, output, dt, date_entry):
        """Assert that the given output is equal to the expected success
        message for a Tweet posted as the date_entry-th Tweet on the
        given date dt."""
        tweets = get_tweets_on_date(dt, date_entry=date_entry)
        self.assertEqual(len(tweets), 1)
        tweet = tweets[0]
        message = (
            f"Posted {tweet['Word']} with Tweet ID {tweet['TweetId']} and "
            f"internal ID {tweet['Id']} as entry {tweet['DateEntry']} on date "
            f"{tweet['Date']}.")
        self.assertEqual(output, message)

    def extract_success_details(self, output):
        """Given a valid success message, extract and return the word,
        Tweet ID, internal ID, entry number, and date."""
        pattern = (
            "Posted (.*) with Tweet ID (.*) and internal ID (.*) as entry "
            "(.*) on date (.*).")
        return re.search(pattern, output).groups()

    @patch("main.put_item")
    def test_first_tweet_sets_earliest_tweet_date_setting(self, mock_put_item):
        """Test that, if the setting for the earliest Tweet date is
        unset, it gets set to the date of the Tweet being posted."""
        today = date.today()

        table = DynamoDBTable.UNPROCESSED_WORDS
        words = [
            ("再见", "zài jiàn"),
            ("你好", "nǐ hǎo"),
        ]
        for word in words:
            item = {
                "Id": str(uuid.uuid4()),
                "Characters": word[0],
                "Pinyin": word[1],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            }
            put_item(table, item)

        # Patch the method for putting an item in DynamoDB to raise an
        # AWSClientError if the table is the "Settings" table and the
        # earliest tweet date is already set.
        def raise_aws_client_error_conditionally(table, item):
            if (table.value.name == DynamoDBTable.SETTINGS.value.name and
                    get_earliest_tweet_date() is not None):
                raise AWSClientError("This exception is expected.")
            return put_item(table, item)
        mock_put_item.side_effect = raise_aws_client_error_conditionally

        # The first run should set the setting.
        self.assertIsNone(get_earliest_tweet_date())

        out, err = StringIO(), StringIO()
        with redirect_stdout(out):
            with redirect_stderr(err):
                run_twitter_bot()
        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, today, 0)

        earliest_tweet_date = get_earliest_tweet_date()
        self.assertIsNotNone(earliest_tweet_date)
        self.assertEqual(earliest_tweet_date, str(date.today()))

        # Further runs should not attempt to set the setting.
        out, err = StringIO(), StringIO()
        with redirect_stdout(out):
            with redirect_stderr(err):
                run_twitter_bot()

        # The mocked exception should not have been raised, since its
        # parent code block should not have been entered.
        self.assertFalse(err.getvalue())
        self.assert_success_message(out.getvalue(), today, 1)

        # Two new Tweets should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 2)
        for created_tweet in created_tweets:
            self.created_tweets.add(created_tweet["id_str"])

    def test_no_previous_tweets_exist(self):
        """Test that, if there are no previous Tweets to include in this
        Tweet, the created Tweet has the expected body."""
        table = DynamoDBTable.UNPROCESSED_WORDS
        item = {
            "Id": str(uuid.uuid4()),
            "Characters": "再见",
            "Pinyin": "zài jiàn",
            "InsertionTimestamp": utc_seconds_since_the_epoch(),
        }
        put_item(table, item)

        out, err = StringIO(), StringIO()
        with redirect_stdout(out):
            with redirect_stderr(err):
                run_twitter_bot()
        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, date.today(), 0)

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)
        created_tweet = created_tweets[0]
        tweet_id_str = created_tweet["id_str"]
        self.created_tweets.add(tweet_id_str)

        # It should have the expected body.
        mdbg_parser = MDBGParser(item["Characters"], pinyin=item["Pinyin"])
        try:
            mdbg_parser.run()
        except MDBGError:
            self.fail(f"Failed to retrieve dictionary data for comparison.")
        previous_tweets = self.previous_tweets(
            last_week={}, last_month={}, random={})
        body = generate_tweet_body(mdbg_parser, previous_tweets)
        self.assertEqual(created_tweet["full_text"], body)

        # A record of the Tweet should have been created.
        _, _, internal_id, _, _ = self.extract_success_details(output)
        today = date.today()
        tweets = get_tweets_on_date(today)
        self.assertEqual(len(tweets), 1)
        tweet = tweets[0]
        self.assertEqual(tweet["Id"], internal_id)
        self.assertEqual(tweet["TweetId"], tweet_id_str)
        self.assertEqual(tweet["Date"], str(today))
        self.assertEqual(tweet["DateEntry"], 0)
        self.assertEqual(tweet["Word"], item["Characters"])
        table = DynamoDBTable.TWEETS
        self.created_items[table.value.name].append({
            "Id": tweet["Id"],
            "Date": tweet["Date"],
        })

    def test_all_previous_entries_exist(self):
        """Test that, when all previous entries exist, the created Tweet
        has the expected body."""
        today = date.today()
        days_since_last_week = 7
        days_since_last_month = 30
        days_since_random = 15
        last_week_tweet, last_month_tweet, random_tweet = {}, {}, {}
        entries = [
            ("影响力", "yǐngxiǎnglì"),
            ("常识", "chángshì"),
            ("同胞", "tóngbāo"),
            ("孩子", "háizi"),
        ]

        # Upload four words, three of which are previous entries, and one
        # to be posted today.
        table = DynamoDBTable.UNPROCESSED_WORDS
        items = []
        for i, entry in enumerate(entries):
            items.append({
                "Id": str(uuid.uuid4()),
                "Characters": entry[0],
                "Pinyin": entry[1],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            })
        batch_put_items(table, items)

        # Post three previous Tweets: 30 days ago, a random number of
        # days ago (15), and 7 days ago.
        table = DynamoDBTable.TWEETS
        days = [days_since_last_month, days_since_random, days_since_last_week]
        for num_days in days:
            # Patch the method for today's date to return a past date.
            # Source: https://stackoverflow.com/a/25652721
            dt = today - timedelta(days=num_days)
            with patch("main.date") as mock_date:
                mock_date.today.return_value = dt
                mock_date.side_effect = lambda *args, **kwargs: date(
                    *args, **kwargs)
                out, err = StringIO(), StringIO()
                with redirect_stdout(out):
                    with redirect_stderr(err):
                        run_twitter_bot()
                mock_date.today.assert_called()

            self.assertFalse(err.getvalue())
            output = out.getvalue()
            self.assert_success_message(output, dt, 0)

            word, tweet_id, internal_id, _, _ = \
                self.extract_success_details(output)
            self.created_tweets.add(tweet_id)
            self.created_items[table.value.name].append({
                "Id": internal_id,
                "Date": dt.strftime(DATE_FORMAT),
            })

            if num_days == days_since_last_week:
                last_week_tweet["word"] = word
                last_week_tweet["tweet_id"] = tweet_id
                last_week_tweet["url"] = tweet_url(self.username, tweet_id)
            elif num_days == days_since_last_month:
                last_month_tweet["word"] = word
                last_month_tweet["tweet_id"] = tweet_id
                last_month_tweet["url"] = tweet_url(self.username, tweet_id)
            elif num_days == days_since_random:
                random_tweet["word"] = word
                random_tweet["tweet_id"] = tweet_id
                random_tweet["url"] = tweet_url(self.username, tweet_id)

        # The earliest Tweet date should have been set.
        self.created_items[DynamoDBTable.SETTINGS.value.name].append({
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE})

        # Post a Tweet today.
        with patch("main.random_dates_in_range") as mock_random_dates:
            # Patch the method for random dates to return the desired date.
            random_dt = today - timedelta(days=days_since_random)
            mock_random_dates.return_value = [random_dt]
            out, err = StringIO(), StringIO()
            with redirect_stdout(out):
                with redirect_stderr(err):
                    run_twitter_bot()

        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, today, 0)

        word, tweet_id, internal_id, _, _ = \
            self.extract_success_details(output)
        self.created_tweets.add(tweet_id)
        self.created_items[DynamoDBTable.TWEETS.value.name].append({
            "Id": internal_id,
            "Date": today.strftime(DATE_FORMAT),
        })

        # Assert that today's Tweet has the expected body.
        mdbg_parser = MDBGParser(word)
        try:
            mdbg_parser.run()
        except MDBGError:
            self.fail(f"Failed to retrieve dictionary data for comparison.")
        previous_tweets = self.previous_tweets(
            last_week=last_week_tweet, last_month=last_month_tweet,
            random=random_tweet)
        expected_body = generate_tweet_body(mdbg_parser, previous_tweets)

        tweet = self.twitter_api.get_recent_tweets(self.username)[0]
        actual_body = tweet["full_text"]

        # URLs are shortened by Twitter, so remove them from both.
        for tweet in (last_week_tweet, last_month_tweet, random_tweet):
            expected_body = expected_body.replace(tweet["url"], "")
        actual_body = re.sub("https://t.co/([a-zA-Z0-9]+)", "", actual_body)

        self.assertEqual(expected_body, actual_body)

    def test_some_previous_entries_exist(self):
        """Test that, when some previous entries exist, the created
        Tweet has the expected body."""
        today = date.today()
        days_since_random = 15
        days_since_last_month = 30
        last_month_tweet = {}
        entries = [
            ("影响力", "yǐngxiǎnglì"),
            ("孩子", "háizi"),
        ]

        # Upload two words, one of which is a previous entry, and one to
        # be posted today.
        table = DynamoDBTable.UNPROCESSED_WORDS
        items = []
        for i, entry in enumerate(entries):
            items.append({
                "Id": str(uuid.uuid4()),
                "Characters": entry[0],
                "Pinyin": entry[1],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            })
        batch_put_items(table, items)

        # Post one previous Tweet: 30 days ago.
        table = DynamoDBTable.TWEETS
        # Patch the method for today's date to return a past date.
        # Source: https://stackoverflow.com/a/25652721
        dt = today - timedelta(days=days_since_last_month)
        with patch("main.date") as mock_date:
            mock_date.today.return_value = dt
            mock_date.side_effect = lambda *args, **kwargs: date(
                *args, **kwargs)
            out, err = StringIO(), StringIO()
            with redirect_stdout(out):
                with redirect_stderr(err):
                    run_twitter_bot()
            mock_date.today.assert_called()

        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, dt, 0)

        word, tweet_id, internal_id, _, _ = \
            self.extract_success_details(output)
        self.created_tweets.add(tweet_id)
        self.created_items[table.value.name].append({
            "Id": internal_id,
            "Date": dt.strftime(DATE_FORMAT),
        })

        last_month_tweet["word"] = word
        last_month_tweet["tweet_id"] = tweet_id
        last_month_tweet["url"] = tweet_url(self.username, tweet_id)

        # The earliest Tweet date should have been set.
        self.created_items[DynamoDBTable.SETTINGS.value.name].append({
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE})

        # Post a Tweet today.
        with patch("main.random_dates_in_range") as mock_random_dates:
            # Patch the method for random dates to return the desired date.
            random_dt = today - timedelta(days=days_since_random)
            mock_random_dates.return_value = [random_dt]
            out, err = StringIO(), StringIO()
            with redirect_stdout(out):
                with redirect_stderr(err):
                    run_twitter_bot()

        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, today, 0)

        word, tweet_id, internal_id, _, _ = \
            self.extract_success_details(output)
        self.created_tweets.add(tweet_id)
        self.created_items[DynamoDBTable.TWEETS.value.name].append({
            "Id": internal_id,
            "Date": today.strftime(DATE_FORMAT),
        })

        # Assert that today's Tweet has the expected body.
        mdbg_parser = MDBGParser(word)
        try:
            mdbg_parser.run()
        except MDBGError:
            self.fail(f"Failed to retrieve dictionary data for comparison.")
        previous_tweets = self.previous_tweets(
            last_week={}, last_month=last_month_tweet, random={})
        expected_body = generate_tweet_body(mdbg_parser, previous_tweets)

        tweet = self.twitter_api.get_recent_tweets(self.username)[0]
        actual_body = tweet["full_text"]

        # URLs are shortened by Twitter, so remove them from both.
        expected_body = expected_body.replace(last_month_tweet["url"], "")
        actual_body = re.sub("https://t.co/([a-zA-Z0-9]+)", "", actual_body)

        self.assertEqual(expected_body, actual_body)
        self.assertNotIn("Last Week", actual_body)
        self.assertIn("Last Month", actual_body)
        self.assertNotIn("Random", actual_body)

    def test_simulate_one_day(self):
        """Test that the i-th Tweet on a given day references the i-th
        Tweets of previous days."""
        today = date.today()
        days_since_last_week = 7
        days_since_last_month = 30
        days_since_random = 15
        entries = [
            ("影响力", "yǐngxiǎnglì"),
            ("常识", "chángshì"),
            ("同胞", "tóngbāo"),
            ("孩子", "háizi"),
            ("感动", "gǎndòng"),
            ("快乐", "kuàilè"),
            ("大学生", "dàxuéshēng"),
            ("时间表", "shíjiānbiǎo"),
            ("歌", "gē"),
        ]

        # Upload nine words, six of which are previous entries, and
        # three to be posted today.
        table = DynamoDBTable.UNPROCESSED_WORDS
        items = []
        for i, entry in enumerate(entries):
            items.append({
                "Id": str(uuid.uuid4()),
                "Characters": entry[0],
                "Pinyin": entry[1],
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            })
        batch_put_items(table, items)

        last_week_tweets, last_month_tweets, random_tweets = [], [], []

        # Post six previous Tweets: three 30 days ago, two a random
        # number of days ago (15), and one 7 days ago.
        days = [
            (days_since_last_month, 3),
            (days_since_random, 2),
            (days_since_last_week, 1),
        ]
        table = DynamoDBTable.TWEETS
        for num_days, num_tweets in days:
            for date_entry in range(num_tweets):
                # Patch the method for today's date to return a past date.
                # Source: https://stackoverflow.com/a/25652721
                dt = today - timedelta(days=num_days)
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = dt
                    mock_date.side_effect = lambda *args, **kwargs: date(
                        *args, **kwargs)
                    out, err = StringIO(), StringIO()
                    with redirect_stdout(out):
                        with redirect_stderr(err):
                            run_twitter_bot()
                    mock_date.today.assert_called()

                self.assertFalse(err.getvalue())
                output = out.getvalue()
                self.assert_success_message(output, dt, date_entry)

                word, tweet_id, internal_id, _, _ = \
                    self.extract_success_details(output)
                self.created_tweets.add(tweet_id)
                self.created_items[table.value.name].append({
                    "Id": internal_id,
                    "Date": dt.strftime(DATE_FORMAT),
                })

                tweet = {
                    "word": word,
                    "tweet_id": tweet_id,
                    "url": tweet_url(self.username, tweet_id)
                }
                if num_days == days_since_last_week:
                    last_week_tweets.append(tweet)
                elif num_days == days_since_last_month:
                    last_month_tweets.append(tweet)
                elif num_days == days_since_random:
                    random_tweets.append(tweet)

        # The earliest Tweet date should have been set.
        self.created_items[DynamoDBTable.SETTINGS.value.name].append({
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE})

        # Post three Tweets today.
        for date_entry in range(3):
            with patch("main.random_dates_in_range") as mock_random_dates:
                # Patch the method for random dates to return the desired date.
                random_dt = today - timedelta(days=days_since_random)
                mock_random_dates.return_value = [random_dt]
                out, err = StringIO(), StringIO()
                with redirect_stdout(out):
                    with redirect_stderr(err):
                        run_twitter_bot()

            self.assertFalse(err.getvalue())
            output = out.getvalue()
            self.assert_success_message(output, today, date_entry)

            word, tweet_id, internal_id, _, _ = \
                self.extract_success_details(output)
            self.created_tweets.add(tweet_id)
            self.created_items[DynamoDBTable.TWEETS.value.name].append({
                "Id": internal_id,
                "Date": today.strftime(DATE_FORMAT),
            })

            last_week_tweet = (
                last_week_tweets[date_entry]
                if date_entry < len(last_week_tweets)
                else {})
            last_month_tweet = (
                last_month_tweets[date_entry]
                if date_entry < len(last_month_tweets)
                else {})
            random_tweet = (
                random_tweets[date_entry]
                if date_entry < len(random_tweets)
                else {})

            # Assert that today's Tweet has the expected body.
            mdbg_parser = MDBGParser(word)
            try:
                mdbg_parser.run()
            except MDBGError:
                self.fail(
                    f"Failed to retrieve dictionary data for comparison.")
            previous_tweets = self.previous_tweets(
                last_week=last_week_tweet, last_month=last_month_tweet,
                random=random_tweet)
            expected_body = generate_tweet_body(mdbg_parser, previous_tweets)

            tweet = self.twitter_api.get_recent_tweets(self.username)[0]
            actual_body = tweet["full_text"]

            # URLs are shortened by Twitter, so remove them from both.
            for tweet in (last_week_tweet, last_month_tweet, random_tweet):
                if "url" in tweet:
                    expected_body = expected_body.replace(tweet["url"], "")
            actual_body = re.sub("https://t.co/([a-zA-Z0-9]+)", "",
                                 actual_body)

            self.assertEqual(expected_body, actual_body)


class TestGenerateTweetBody(TestCase):
    """A class for testing the method for generating the body of a
    Tweet."""

    def setUp(self):
        self.mdbg_parser = MDBGParser("你好", pinyin="nǐhǎo")
        self.mdbg_parser.definitions = ["hello"]
        self.previous_tweets = namedtuple(
            "PreviousTweets", "last_week last_month random")
        self.url = "http://twitter.com/dummy_url"

    @staticmethod
    def tweet_body_length(body, word, last_week, last_month, random):
        """Return the character count of the Tweet in Twitter's terms.
        In particular, Chinese characters are counted twice, and URLs
        are modified to have length TWEET_URL_LENGTH = 23."""
        count = len(body)
        # Chinese characters are counted twice.
        count = count + len(word)
        entries = {
            "Last Week": last_week,
            "Last Month": last_month,
            "Random": random,
        }
        for entry, values in entries.items():
            if entry in body:
                count = count + len(values["word"])
                count = count - len(values["url"]) + TWEET_URL_LENGTH
        return count

    def test_missing_or_bad_previous_tweets_omitted(self):
        """Test that, if one or more previous Tweets is not provided or
        is badly formatted, its corresponding entry is omitted from the
        output."""
        previous_tweets = self.previous_tweets(
            last_week=None, last_month=None, random=None)
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)
        self.assertNotIn("Last Week", body)
        self.assertNotIn("Last Month", body)
        self.assertNotIn("Random", body)

        previous_tweets = self.previous_tweets(
            last_week=None, last_month={"bad": "entry"}, random=None)
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)
        self.assertNotIn("Last Week", body)
        self.assertNotIn("Last Month", body)
        self.assertNotIn("Random", body)

        previous_tweets = self.previous_tweets(
            last_week=None, last_month={"word": "我", "url": self.url},
            random=None)
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)
        self.assertNotIn("Last Week", body)
        self.assertIn("Last Month", body)
        self.assertNotIn("Random", body)

    def test_overlong_previous_entry(self):
        """Test that, if a previous Tweet entry uses too many
        characters, subsequent entries are ignored."""
        last_week = {
            # The word is long enough to cause other previous entries to be
            # ignored, but not the current word.
            "word": "我" * 111,
            "url": self.url
        }
        last_month = last_week.copy()
        random = last_month.copy()

        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)
        self.assertIn("Last Week", body)
        self.assertNotIn("Last Month", body)
        self.assertNotIn("Random", body)

        expected_length = 280
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)

        last_week["word"] = last_week["word"] + "我"
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)
        self.assertNotIn("Last Week", body)

        expected_length = 277
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        self.assertNotIn("Last Week", body)
        self.assertNotIn("Last Month", body)
        self.assertIn("Random", body)

    def test_overlong_current_entry(self):
        """Test that, if the current entry uses too many characters, an
        exception is raised."""
        # Chinese characters are counted as two by Twitter.
        self.mdbg_parser.simplified = "我" * (TWEET_MAX_CHARS // 2)

        previous_tweets = self.previous_tweets(
            last_week={}, last_month={}, random={})

        with self.assertRaises(ValueError):
            generate_tweet_body(self.mdbg_parser, previous_tweets)

    def test_overlong_definitions_all(self):
        """Test that, if all of the current entry's definitions use too
        many characters, none are included."""
        last_week = {"word": "我", "url": self.url}
        last_month = last_week.copy()
        random = last_month.copy()
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)

        self.mdbg_parser.definitions = [
            "_" * TWEET_MAX_CHARS,
            "-" * TWEET_MAX_CHARS,
            "." * TWEET_MAX_CHARS,
            "," * TWEET_MAX_CHARS,
        ]
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)

        expected_length = 131
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        expected_body = (
            "你好 (nǐhǎo)\n"
            "\n"
            "Last Week: 我 (http://twitter.com/dummy_url)\n"
            "Last Month: 我 (http://twitter.com/dummy_url)\n"
            "Random: 我 (http://twitter.com/dummy_url)")
        self.assertEqual(expected_body, body)

    def test_overlong_definitions_except_one(self):
        """Test that the first definition for the current entry that
        does not use too many characters is used."""
        last_week = {"word": "我", "url": self.url}
        last_month = last_week.copy()
        random = last_month.copy()
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)

        self.mdbg_parser.definitions = [
            "_" * TWEET_MAX_CHARS,
            "-" * TWEET_MAX_CHARS,
            "." * TWEET_MAX_CHARS,
            "," * TWEET_MAX_CHARS,
            "hello",
        ]
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)

        expected_length = 138
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        expected_body = (
            "你好 (nǐhǎo): hello\n"
            "\n"
            "Last Week: 我 (http://twitter.com/dummy_url)\n"
            "Last Month: 我 (http://twitter.com/dummy_url)\n"
            "Random: 我 (http://twitter.com/dummy_url)")
        self.assertEqual(expected_body, body)

    def test_further_definitions_included_after_previous_entries(self):
        """Test that definitions after the first one are only considered
        once previous entries have been added to the body."""
        last_week = {"word": "我", "url": self.url}
        last_month = last_week.copy()
        random = last_month.copy()
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)

        # Test definitions do not match actual word.
        self.mdbg_parser.definitions = [
            "hello",
            "_" * TWEET_MAX_CHARS,
            "-" * TWEET_MAX_CHARS,
            "hi",
            "." * TWEET_MAX_CHARS,
            "," * TWEET_MAX_CHARS,
            "hey",
            # Were this the first non-overlong definition, it would have been
            # included in the first pass. However, because it is considered
            # after previous entries have been added, it causes overflow.
            "_" * (TWEET_MAX_CHARS - 147),
        ]
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)

        expected_length = 147
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        expected_body = (
            "你好 (nǐhǎo): hello; hi; hey\n"
            "\n"
            "Last Week: 我 (http://twitter.com/dummy_url)\n"
            "Last Month: 我 (http://twitter.com/dummy_url)\n"
            "Random: 我 (http://twitter.com/dummy_url)")
        self.assertEqual(expected_body, body)

        # Remove a previous entry and try again. This time, the last definition
        # should be included.
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random={})
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)

        expected_length = 245
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        last_definition = self.mdbg_parser.definitions[-1]
        expected_body = (
            f"你好 (nǐhǎo): hello; hi; hey; {last_definition}\n"
            f"\n"
            f"Last Week: 我 (http://twitter.com/dummy_url)\n"
            f"Last Month: 我 (http://twitter.com/dummy_url)")
        self.assertEqual(expected_body, body)

    def test_urls_truncated_to_twitter_length(self):
        """Test that, because Twitter truncates URL lengths to
        settings.TWEET_URL_LENGTH (currently 23) characters, overlong
        URLs in the body are accepted."""
        url = (
            "https://twitter.com/a/long/url/that/will/get/truncated/when/"
            "tweet/is/created")
        last_week = {"word": "我", "url": url}
        last_month = last_week.copy()
        random = last_month.copy()
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)

        self.mdbg_parser.definitions = [
            "hello",
            "hi",
            "hey",
        ]
        body = generate_tweet_body(self.mdbg_parser, previous_tweets)

        expected_body = (
            f"你好 (nǐhǎo): hello; hi; hey\n"
            f"\n"
            f"Last Week: 我 ({url})\n"
            f"Last Month: 我 ({url})\n"
            f"Random: 我 ({url})")
        self.assertGreater(len(expected_body), TWEET_MAX_CHARS)

        expected_length = (len(expected_body) +
                           5 -
                           3 * len(url) +
                           3 * TWEET_URL_LENGTH)
        actual_length = self.tweet_body_length(
            body, self.mdbg_parser.simplified, last_week, last_month, random)
        self.assertEqual(expected_length, actual_length)
        self.assertEqual(expected_body, body)


class TestTwitterBotUtils(TestDynamoDBMixin):
    """A class for testing the utility methods of the main
    application."""

    def setUp(self):
        super().setUp()
        self.twitter_api = TwitterAPIClient()
        self.created_tweets = set()

    def test_get_previous_tweets_raises_errors(self):
        """Test that the method for retrieving previous Tweets raises
        the expected errors."""
        with self.assertRaises(TypeError):
            get_previous_tweets("1")
        with self.assertRaises(ValueError):
            get_previous_tweets(-1)

    @patch("main.random_dates_in_range")
    def test_get_previous_tweets_output(self, mock_method):
        """Test that the method for retrieving previous Tweets returns
        the expected output."""

        def assert_result(test, expected, actual):
            """Assert that the retrieved Tweet has the expected format
            and values."""
            test.assertEqual(len(actual), 3)
            test.assertIn("tweet_id", actual)
            test.assertEqual(actual["tweet_id"], expected["TweetId"])
            test.assertIn("word", actual)
            test.assertEqual(actual["word"], expected["Word"])
            test.assertIn("url", actual)
            expected_url = (
                f"https://twitter.com/{TWITTER_USER_USERNAME}/statuses/"
                f"{expected['TweetId']}")
            self.assertEqual(actual["url"], expected_url)

        # Initially, no Tweets exist.
        table = DynamoDBTable.TWEETS
        previous_tweets = get_previous_tweets(0)
        for attr in ("last_week", "last_month", "random"):
            self.assertTrue(hasattr(previous_tweets, attr))
            self.assertFalse(getattr(previous_tweets, attr))

        # Simulate a Tweet created last week.
        dynamodb_id = str(uuid.uuid4())
        tweet_id = self.twitter_api.post_tweet(f"Test tweet {dynamodb_id}")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))
        self.created_tweets.add(tweet_id)

        last_week_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=7)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word1",
        }
        put_item(table, last_week_expected)
        self.created_items[table.value.name].append({
            "Id": last_week_expected["Id"],
            "Date": last_week_expected["Date"]})

        previous_tweets = get_previous_tweets(0)
        last_week_actual = getattr(previous_tweets, "last_week")
        assert_result(self, last_week_expected, last_week_actual)

        # Simulate a Tweet created last month.
        dynamodb_id = str(uuid.uuid4())
        tweet_id = self.twitter_api.post_tweet(f"Test tweet {dynamodb_id}")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))
        self.created_tweets.add(tweet_id)

        last_month_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=30)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word2",
        }
        put_item(table, last_month_expected)
        self.created_items[table.value.name].append({
            "Id": last_month_expected["Id"],
            "Date": last_month_expected["Date"]})

        previous_tweets = get_previous_tweets(0)
        last_week_actual = getattr(previous_tweets, "last_week")
        assert_result(self, last_week_expected, last_week_actual)
        last_month_actual = getattr(previous_tweets, "last_month")
        assert_result(self, last_month_expected, last_month_actual)

        # Simulate a Tweet created at a random previous date.
        dynamodb_id = str(uuid.uuid4())
        tweet_id = self.twitter_api.post_tweet(f"Test tweet {dynamodb_id}")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))
        self.created_tweets.add(tweet_id)

        random_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=100)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word3",
        }
        put_item(table, random_expected)
        self.created_items[table.value.name].append({
            "Id": random_expected["Id"],
            "Date": random_expected["Date"]})

        # Set the earliest Tweet date.
        set_earliest_tweet_date(random_expected["Date"])

        # Modify the method for returning random dates to give the desired one.
        mock_method.return_value = [date.today() - timedelta(days=100)]

        previous_tweets = get_previous_tweets(0)
        last_week_actual = getattr(previous_tweets, "last_week")
        assert_result(self, last_week_expected, last_week_actual)
        last_month_actual = getattr(previous_tweets, "last_month")
        assert_result(self, last_month_expected, last_month_actual)
        random_actual = getattr(previous_tweets, "random")
        assert_result(self, random_expected, random_actual)

        # The mocked method should have been used.
        mock_method.assert_called()

        # Retrieving a different DateEntry should return different results.
        last_month_expected = {
            "Id": last_month_expected["Id"],
            "TweetId": last_month_expected["TweetId"],
            "Date": (date.today() - timedelta(days=30)).strftime(DATE_FORMAT),
            "DateEntry": 1,
            "Word": "word2",
        }
        put_item(table, last_month_expected)

        previous_tweets = get_previous_tweets(0)
        self.assertFalse(previous_tweets.last_month)
        previous_tweets = get_previous_tweets(1)
        self.assertTrue(previous_tweets.last_month)

        # Delete created Tweets from Twitter.
        for tweet_id in self.created_tweets:
            self.twitter_api.delete_tweet(tweet_id)
            self.assertFalse(self.twitter_api.tweet_exists(tweet_id))

    def test_get_tweets_on_random_date_raises_errors(self):
        """Test that the method for retrieving the Tweets tweeted on a
        random date raises the expected errors."""
        earliest_tweet_date = (date.today() - timedelta(days=5))
        set_earliest_tweet_date(earliest_tweet_date.strftime(DATE_FORMAT))

        with self.assertRaises(TypeError):
            get_tweets_on_random_date(date_entry="1")
        with self.assertRaises(ValueError):
            get_tweets_on_random_date(date_entry=-1)
        with self.assertRaises(ValueError):
            get_tweets_on_random_date(date_entry=TWEETS_PER_DAY)
        with self.assertRaises(TypeError):
            get_tweets_on_random_date(num_tries="1")
        with self.assertRaises(ValueError):
            get_tweets_on_random_date(num_tries=-1)

    def test_get_tweets_on_random_date_output(self):
        """Test that the method for retrieving the Tweets tweeted on a
        random date returns the expected output."""
        # If there was no earliest Tweet, the output should be empty.
        self.assertFalse(get_tweets_on_random_date(date_entry=0))

        earliest_tweet_date = (date.today() - timedelta(days=5))
        set_earliest_tweet_date(earliest_tweet_date.strftime(DATE_FORMAT))

        self.assertFalse(get_tweets_on_random_date(date_entry=0))

        # Create some Tweets and check that they can be retrieved.
        table = DynamoDBTable.TWEETS
        items = []
        for i in range(5):
            item = {
                "Id": str(i),
                "TweetId": str(i),
                "Date": (earliest_tweet_date + timedelta(days=i)).strftime(
                    DATE_FORMAT),
                "DateEntry": 0,
                "Word": f"word{i}",
            }
            items.append(item)
            key = {
                "Id": item["Id"],
                "Date": item["Date"],
            }
            self.created_items[table.value.name].append(key)

        batch_put_items(table, items[:2])
        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(2)]))

        batch_put_items(table, items[2:])
        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(5)]))

        # Check that Tweets with different DateEntry values can be retrieved.
        self.assertFalse(get_tweets_on_random_date(date_entry=1))
        self.assertFalse(get_tweets_on_random_date(date_entry=2))

        items[1]["DateEntry"] = 1
        items[2]["DateEntry"] = 2
        batch_put_items(DynamoDBTable.TWEETS, items[1:3])

        tweets = get_tweets_on_random_date(date_entry=0)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in [0, 3, 4]]))

        tweets = get_tweets_on_random_date(date_entry=1)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0]["Id"], str(1))

        tweets = get_tweets_on_random_date(date_entry=2)
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0]["Id"], str(2))

        tweets = get_tweets_on_random_date(date_entry=None)
        self.assertEqual(len(tweets), 1)
        self.assertIn(tweets[0]["Id"], set([str(i) for i in range(5)]))

        dynamodb = boto3.resource(
            AWSResource.DYNAMO_DB, endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
        table = dynamodb.Table(DynamoDBTable.TWEETS.value.name)
        with table.batch_writer() as batch:
            for item in items:
                key = {
                    "Id": item["Id"],
                    "Date": item["Date"],
                }
                batch.delete_item(Key=key)

        self.created_items[DynamoDBTable.SETTINGS.value.name].append({
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE})
