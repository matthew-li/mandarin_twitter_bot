from aws_client import AWSClientError
from aws_client import get_earliest_tweet_date
from aws_client import get_tweets_on_date
from aws_client import put_item
from collections import namedtuple
from constants import DynamoDBTable
from constants import TwitterBotExitCodes
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date
from datetime import timedelta
from io import StringIO
from main import generate_tweet_body
from main import main as run_twitter_bot
from mdbg_parser import MDBGError
from mdbg_parser import MDBGParser
from settings import TWITTER_USER_USERNAME
from tests.test_aws_client import TestDynamoDBMixin
from tests.test_twitter_bot.utils import delete_created_tweets
from twitter_api_client import TwitterAPIClient
from unittest.mock import patch
from utils import tweet_url
import re

"""A test module for testing that the main application behaves as
expected."""


class TestTwitterBot(TestDynamoDBMixin):
    """A class for testing the main method of the main application."""

    def setUp(self):
        super().setUp()
        self.username = TWITTER_USER_USERNAME
        self.twitter_api = TwitterAPIClient()
        self.previous_tweets = namedtuple(
            "PreviousTweets", "last_week last_month random")
        self.addCleanup(delete_created_tweets)

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

    @staticmethod
    def extract_success_details(output):
        """Given a valid success message, extract and return the word,
        Tweet ID, internal ID, entry number, and date."""
        pattern = (
            "Posted (.*) with Tweet ID (.*) and internal ID (.*) as entry "
            "(.*) on date (.*).")
        return re.search(pattern, output).groups()

    def regenerate_tweet_body(self, characters, pinyin="", last_week={},
                              last_month={}, random={}):
        """Given details about the current and previous entries, return
        the expected Tweet body."""
        mdbg_parser = MDBGParser(characters, pinyin=pinyin)
        try:
            mdbg_parser.run()
        except MDBGError:
            self.fail(f"Failed to retrieve dictionary data for comparison.")
        previous_tweets = self.previous_tweets(
            last_week=last_week, last_month=last_month, random=random)
        return generate_tweet_body(mdbg_parser, previous_tweets)

    def run_twitter_bot_successfully(self, dt, date_entry):
        """Run the Twitter bot, expecting a success message and no
        errors. Return the word, Tweet ID, internal ID, entry number,
        and date."""
        out, err = StringIO(), StringIO()
        with redirect_stdout(out):
            with redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    run_twitter_bot()
                self.assertEqual(cm.exception.code, TwitterBotExitCodes.OK)
        self.assertFalse(err.getvalue())
        output = out.getvalue()
        self.assert_success_message(output, dt, date_entry)
        word, tweet_id, internal_id, entry_number, dt = \
            self.extract_success_details(output)
        self.record_created_tweet(internal_id, dt)
        return word, tweet_id, internal_id, entry_number, dt

    @patch("main.put_item")
    def test_first_tweet_sets_earliest_tweet_date_setting(self, mock_put_item):
        """Test that, if the setting for the earliest Tweet date is
        unset, it gets set to the date of the Tweet being posted."""
        today = date.today()

        words = [
            ("再见", "zài jiàn"),
            ("你好", "nǐ hǎo"),
        ]
        self.create_words(words)

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

        _, tweet_id, internal_id, _, _ = \
            self.run_twitter_bot_successfully(today, 0)

        earliest_tweet_date = get_earliest_tweet_date()
        self.assertIsNotNone(earliest_tweet_date)
        self.assertEqual(earliest_tweet_date, str(date.today()))

        # Further runs should not attempt to set the setting. The mocked
        # exception should not have been raised, since its parent code
        # block should not have been entered.
        self.run_twitter_bot_successfully(today, 1)

    def test_no_previous_tweets_exist(self):
        """Test that, if there are no previous Tweets to include in this
        Tweet, the created Tweet has the expected body."""
        today = date.today()

        words = [
            ("再见", "zài jiàn"),
        ]
        self.create_words(words)

        _, _, internal_id, _, _ = self.run_twitter_bot_successfully(today, 0)

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)
        created_tweet = created_tweets[0]
        tweet_id_str = created_tweet["id_str"]

        # It should have the expected body.
        characters, pinyin = words[0]
        expected_body = self.regenerate_tweet_body(characters, pinyin=pinyin)
        self.assertEqual(created_tweet["full_text"], expected_body)

        # A record of the Tweet should have been created.
        tweets = get_tweets_on_date(today)
        self.assertEqual(len(tweets), 1)
        tweet = tweets[0]
        self.assertEqual(tweet["Id"], internal_id)
        self.assertEqual(tweet["TweetId"], tweet_id_str)
        self.assertEqual(tweet["Date"], str(today))
        self.assertEqual(tweet["DateEntry"], 0)
        self.assertEqual(tweet["Word"], characters)

    def test_all_previous_entries_exist(self):
        """Test that, when all previous entries exist, the created Tweet
        has the expected body."""
        today = date.today()
        days_since_last_week = 7
        days_since_last_month = 30
        days_since_random = 15
        last_week_tweet, last_month_tweet, random_tweet = {}, {}, {}

        # Upload four words, three of which are previous entries, and one
        # to be posted today.
        words = [
            ("影响力", "yǐngxiǎnglì"),
            ("常识", "chángshì"),
            ("同胞", "tóngbāo"),
            ("孩子", "háizi"),
        ]
        self.create_words(words)

        # Post three previous Tweets: 30 days ago, a random number of
        # days ago (15), and 7 days ago.
        days = [days_since_last_month, days_since_random, days_since_last_week]
        for num_days in days:
            # Patch the method for today's date to return a past date.
            # Source: https://stackoverflow.com/a/25652721
            dt = today - timedelta(days=num_days)
            with patch("main.date") as mock_date:
                mock_date.today.return_value = dt
                mock_date.side_effect = lambda *args, **kwargs: date(
                    *args, **kwargs)
                word, tweet_id, internal_id, _, _ = \
                    self.run_twitter_bot_successfully(dt, 0)
                mock_date.today.assert_called()

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

        # Post a Tweet today.
        with patch("main.random_dates_in_range") as mock_random_dates:
            # Patch the method for random dates to return the desired date.
            random_dt = today - timedelta(days=days_since_random)
            mock_random_dates.return_value = [random_dt]
            word, tweet_id, internal_id, _, _ = \
                self.run_twitter_bot_successfully(today, 0)

        # Assert that today's Tweet has the expected body.
        expected_body = self.regenerate_tweet_body(
            word, last_week=last_week_tweet, last_month=last_month_tweet,
            random=random_tweet)

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

        # Upload two words, one of which is a previous entry, and one to
        # be posted today.
        words = [
            ("影响力", "yǐngxiǎnglì"),
            ("孩子", "háizi"),
        ]
        self.create_words(words)

        # Post one previous Tweet: 30 days ago.
        # Patch the method for today's date to return a past date.
        # Source: https://stackoverflow.com/a/25652721
        dt = today - timedelta(days=days_since_last_month)
        with patch("main.date") as mock_date:
            mock_date.today.return_value = dt
            mock_date.side_effect = lambda *args, **kwargs: date(
                *args, **kwargs)
            word, tweet_id, internal_id, _, _ = \
                self.run_twitter_bot_successfully(dt, 0)
            mock_date.today.assert_called()

        last_month_tweet["word"] = word
        last_month_tweet["tweet_id"] = tweet_id
        last_month_tweet["url"] = tweet_url(self.username, tweet_id)

        # Post a Tweet today.
        with patch("main.random_dates_in_range") as mock_random_dates:
            # Patch the method for random dates to return the desired date.
            random_dt = today - timedelta(days=days_since_random)
            mock_random_dates.return_value = [random_dt]
            word, tweet_id, internal_id, _, _ = \
                self.run_twitter_bot_successfully(today, 0)

        # Assert that today's Tweet has the expected body.
        expected_body = self.regenerate_tweet_body(
            word, last_month=last_month_tweet)

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

        # Upload nine words, six of which are previous entries, and
        # three to be posted today.
        words = [
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
        self.create_words(words)

        last_week_tweets, last_month_tweets, random_tweets = [], [], []

        # Post six previous Tweets: three 30 days ago, two a random
        # number of days ago (15), and one 7 days ago.
        days = [
            (days_since_last_month, 3),
            (days_since_random, 2),
            (days_since_last_week, 1),
        ]
        for num_days, num_tweets in days:
            for date_entry in range(num_tweets):
                # Patch the method for today's date to return a past date.
                # Source: https://stackoverflow.com/a/25652721
                dt = today - timedelta(days=num_days)
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = dt
                    mock_date.side_effect = lambda *args, **kwargs: date(
                        *args, **kwargs)
                    word, tweet_id, internal_id, _, _ = \
                        self.run_twitter_bot_successfully(dt, date_entry)
                    mock_date.today.assert_called()

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

        # Post three Tweets today.
        for date_entry in range(3):
            with patch("main.random_dates_in_range") as mock_random_dates:
                # Patch the method for random dates to return the desired date.
                random_dt = today - timedelta(days=days_since_random)
                mock_random_dates.return_value = [random_dt]
                word, tweet_id, internal_id, _, _ = \
                    self.run_twitter_bot_successfully(today, date_entry)

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
            expected_body = self.regenerate_tweet_body(
                word, last_week=last_week_tweet, last_month=last_month_tweet,
                random=random_tweet)

            tweet = self.twitter_api.get_recent_tweets(self.username)[0]
            actual_body = tweet["full_text"]

            # URLs are shortened by Twitter, so remove them from both.
            for tweet in (last_week_tweet, last_month_tweet, random_tweet):
                if "url" in tweet:
                    expected_body = expected_body.replace(tweet["url"], "")
            actual_body = re.sub("https://t.co/([a-zA-Z0-9]+)", "",
                                 actual_body)

            self.assertEqual(expected_body, actual_body)
