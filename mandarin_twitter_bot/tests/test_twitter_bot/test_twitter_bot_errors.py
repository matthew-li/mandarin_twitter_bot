from contextlib import redirect_stderr
from datetime import date
from io import StringIO
from mandarin_twitter_bot.aws_client import AWSClientError
from mandarin_twitter_bot.aws_client import get_and_delete_unprocessed_word
from mandarin_twitter_bot.aws_client import get_earliest_tweet_date
from mandarin_twitter_bot.aws_client import get_tweets_on_date
from mandarin_twitter_bot.aws_client import put_item
from mandarin_twitter_bot.constants import DynamoDBTable
from mandarin_twitter_bot.constants import TWEETS_PER_DAY
from mandarin_twitter_bot.constants import TwitterBotExitCodes
from mandarin_twitter_bot.main import main as run_twitter_bot
from mandarin_twitter_bot.mdbg_parser import MDBGError
from mandarin_twitter_bot.mdbg_parser import MDBGParser
from mandarin_twitter_bot.settings import DATE_FORMAT
from mandarin_twitter_bot.settings import TWITTER_USER_USERNAME
from mandarin_twitter_bot.tests.test_aws_client import TestDynamoDBMixin
from mandarin_twitter_bot.tests.test_twitter_bot.utils import delete_created_tweets
from mandarin_twitter_bot.twitter_api_client import TwitterAPIClient
from unittest.mock import patch
import uuid

"""A test module for testing that failures in the main application
behave and are handled as expected."""


class TestTwitterBotErrors(TestDynamoDBMixin):
    """A class for testing that the main method of the main application
    handles errors as expected."""

    def setUp(self):
        super().setUp()
        self.username = TWITTER_USER_USERNAME
        self.twitter_api = TwitterAPIClient()
        self.addCleanup(delete_created_tweets)

    def run_twitter_bot_with_errors(self, exit_code):
        """Run the Twitter bot, expecting an error and the given exit
        code. Return the error message."""
        err = StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                run_twitter_bot()
            self.assertEqual(cm.exception.code, exit_code)
        return err.getvalue()

    def test_too_many_tweets_today(self):
        """Test that, if the maximum number of Tweets have already been
        posted today, the application exits."""
        words = [
            ("再见", "zài jiàn"),
        ]
        self.create_words(words)

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
            self.record_created_tweet(tweet["Id"], tweet["Date"])

        exit_code = TwitterBotExitCodes.MAX_TWEETS_EXCEEDED
        error = self.run_twitter_bot_with_errors(exit_code)

        message = (
            "The maximum number of Tweets (3) for today has been exceeded. "
            "Exiting.")
        self.assertEqual(error, message)

        # The UnprocessedWord should not have been processed; it should still
        # be in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word["Characters"], "再见")
        self.assertEqual(unprocessed_word["Pinyin"], "zài jiàn")

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
        exit_code = TwitterBotExitCodes.NO_WORDS_LEFT
        error = self.run_twitter_bot_with_errors(exit_code)

        message = "There are no words left to process. Exiting."
        self.assertEqual(error, message)

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
        words = [
            ("12345", "12345"),
        ]
        self.create_words(words)

        # Patch the method for running the dictionary parser to raise an error.
        def raise_mdbg_error():
            raise MDBGError("This exception is expected.")
        mock_run.side_effect = raise_mdbg_error

        exit_code = TwitterBotExitCodes.BAD_DICTIONARY_RESPONSE
        error = self.run_twitter_bot_with_errors(exit_code)

        mock_run.assert_called()

        message = (
            "Failed to retrieve a valid response from the dictionary. "
            "Exiting. Details:\n")
        self.assertTrue(error.startswith(message))
        self.assertIn("Traceback", error)
        self.assertIn("This exception is expected.", error)

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
        words = [
            ("12345", "12345"),
        ]
        self.create_words(words)

        exit_code = TwitterBotExitCodes.NO_DICTIONARY_ENTRY
        error = self.run_twitter_bot_with_errors(exit_code)

        message = (
            f"No dictionary entry was found for {words[0][1]}. Exiting.")
        self.assertEqual(error, message)

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
        words = [
            ("再见", "zài jiàn"),
        ]
        self.create_words(words)

        # Patch the method for posting a Tweet to return None.
        mock_post_tweet.return_value = None

        exit_code = TwitterBotExitCodes.TWEET_FAILED
        error = self.run_twitter_bot_with_errors(exit_code)

        mock_post_tweet.assert_called()

        message = "Failed to create a Tweet with body '再见"
        self.assertTrue(error.startswith(message))
        self.assertTrue(error.endswith("'. Exiting."))

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

    @patch("mandarin_twitter_bot.main.put_item")
    def test_aws_tweet_put_fails(self, mock_put_item):
        """Test that, if the request to put the Tweet in DynamoDB fails,
        the application exits."""
        words = [
            ("再见", "zài jiàn"),
        ]
        self.create_words(words)

        # Patch the method for putting an item in DynamoDB to raise an
        # AWSClientError.
        def raise_aws_client_error(table, item):
            raise AWSClientError("This exception is expected.")
        mock_put_item.side_effect = raise_aws_client_error

        exit_code = TwitterBotExitCodes.DB_FAILED
        error = self.run_twitter_bot_with_errors(exit_code)

        mock_put_item.assert_called()

        message = "Failed to save posted Tweet. Exiting. Details:\n"
        self.assertTrue(error.startswith(message))
        self.assertIn("This exception is expected.", error)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)

        # No record of a Tweet should have been created.
        today = date.today()
        self.assertEqual(len(get_tweets_on_date(today)), 0)

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())

    @patch("mandarin_twitter_bot.aws_client.put_item")
    def test_aws_setting_put_fails(self, mock_put_item):
        """Test that, if the request to put the setting for the earliest
        Tweet date in DynamoDB fails, the application exits."""
        words = [
            ("再见", "zài jiàn"),
        ]
        self.create_words(words)

        # Patch the method for putting an item in DynamoDB to raise an
        # AWSClientError if the table is the "Settings" table.
        def raise_aws_client_error_conditionally(table, item):
            if table.value.name == DynamoDBTable.SETTINGS.value.name:
                raise AWSClientError("This exception is expected.")
            return put_item(table, item)
        mock_put_item.side_effect = raise_aws_client_error_conditionally

        exit_code = TwitterBotExitCodes.DB_FAILED
        error = self.run_twitter_bot_with_errors(exit_code)

        mock_put_item.assert_called()

        message = (
            "Failed to save earliest_tweet_date setting. Exiting. Details:\n")
        self.assertTrue(error.startswith(message))
        self.assertIn("This exception is expected.", error)

        # There should be no UnprocessedWords in the table.
        unprocessed_word = get_and_delete_unprocessed_word()
        self.assertEqual(unprocessed_word, {})

        # A new Tweet should have been created.
        created_tweets = self.twitter_api.get_recent_tweets(
            TWITTER_USER_USERNAME)
        self.assertEqual(len(created_tweets), 1)
        tweet_id_str = created_tweets[0]["id_str"]

        # A record of the Tweet should have been created.
        today = date.today()
        tweets = get_tweets_on_date(today)
        self.assertEqual(len(tweets), 1)
        tweet = tweets[0]
        self.assertEqual(tweet["TweetId"], tweet_id_str)
        self.assertEqual(tweet["Date"], str(today))
        self.assertEqual(tweet["DateEntry"], 0)
        self.assertEqual(tweet["Word"], words[0][0])
        self.record_created_tweet(tweet["Id"], tweet["Date"])

        # The EARLIEST_TWEET_DATE setting should remain unset.
        self.assertIsNone(get_earliest_tweet_date())
