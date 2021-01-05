from datetime import date
from datetime import timedelta
from mandarin_twitter_bot.aws_client import batch_put_items
from mandarin_twitter_bot.aws_client import put_item
from mandarin_twitter_bot.aws_client import set_earliest_tweet_date
from mandarin_twitter_bot.constants import DynamoDBTable
from mandarin_twitter_bot.constants import TWEETS_PER_DAY
from mandarin_twitter_bot.main import get_previous_tweets
from mandarin_twitter_bot.main import get_tweets_on_random_date
from mandarin_twitter_bot.settings import DATE_FORMAT
from mandarin_twitter_bot.settings import TWITTER_USER_USERNAME
from mandarin_twitter_bot.tests.test_aws_client import TestDynamoDBMixin
from mandarin_twitter_bot.tests.test_twitter_bot.utils import delete_created_tweets
from mandarin_twitter_bot.twitter_api_client import TwitterAPIClient
from unittest.mock import patch
import uuid

"""A test module for testing that utility methods behave as expected."""


class TestTwitterBotUtils(TestDynamoDBMixin):
    """A class for testing the utility methods of the main
    application."""

    def setUp(self):
        super().setUp()
        self.username = TWITTER_USER_USERNAME
        self.twitter_api = TwitterAPIClient()
        self.addCleanup(delete_created_tweets)

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

        last_week_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=7)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word1",
        }
        put_item(table, last_week_expected)
        self.record_created_tweet(
            last_week_expected["Id"], last_week_expected["Date"])

        previous_tweets = get_previous_tweets(0)
        last_week_actual = getattr(previous_tweets, "last_week")
        assert_result(self, last_week_expected, last_week_actual)

        # Simulate a Tweet created last month.
        dynamodb_id = str(uuid.uuid4())
        tweet_id = self.twitter_api.post_tweet(f"Test tweet {dynamodb_id}")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))

        last_month_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=30)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word2",
        }
        put_item(table, last_month_expected)
        self.record_created_tweet(
            last_month_expected["Id"], last_month_expected["Date"])

        previous_tweets = get_previous_tweets(0)
        last_week_actual = getattr(previous_tweets, "last_week")
        assert_result(self, last_week_expected, last_week_actual)
        last_month_actual = getattr(previous_tweets, "last_month")
        assert_result(self, last_month_expected, last_month_actual)

        # Simulate a Tweet created at a random previous date.
        dynamodb_id = str(uuid.uuid4())
        tweet_id = self.twitter_api.post_tweet(f"Test tweet {dynamodb_id}")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))

        random_expected = {
            "Id": dynamodb_id,
            "TweetId": tweet_id,
            "Date": (date.today() - timedelta(days=100)).strftime(DATE_FORMAT),
            "DateEntry": 0,
            "Word": "word3",
        }
        put_item(table, random_expected)
        self.record_created_tweet(
            random_expected["Id"], random_expected["Date"])

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
            self.record_created_tweet(item["Id"], item["Date"])

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
