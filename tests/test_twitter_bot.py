from aws_client import batch_put_items
from aws_client import put_item
from collections import namedtuple
from constants import AWSResource
from constants import DynamoDBSettings
from constants import DynamoDBTable
from constants import TWEET_MAX_CHARS
from constants import TWEET_URL_LENGTH
from constants import TWEETS_PER_DAY
from datetime import date
from datetime import timedelta
from main import generate_tweet_body
from main import get_previous_tweets
from main import get_tweets_on_random_date
from mdbg_parser import MDBGParser
from settings import AWS_DYNAMODB_ENDPOINT_URL
from settings import DATE_FORMAT
from settings import TWITTER_USER_USERNAME
from tests.test_aws_client import TestDynamoDBMixin
from twitter_api_client import TwitterAPIClient
from unittest import TestCase
from unittest.mock import patch
import boto3
import uuid

"""A test module for the main functionality of the application."""


class TestTwitterBot(TestDynamoDBMixin):
    """A class for testing the main methods of the application."""

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
        setting = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": random_expected["Date"],
        }
        put_item(DynamoDBTable.SETTINGS, setting)

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
        setting = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": earliest_tweet_date.strftime(DATE_FORMAT)
        }
        put_item(DynamoDBTable.SETTINGS, setting)

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
        setting = {
            "Name": DynamoDBSettings.EARLIEST_TWEET_DATE,
            "Value": earliest_tweet_date.strftime(DATE_FORMAT)
        }
        put_item(DynamoDBTable.SETTINGS, setting)

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

        self.created_items[DynamoDBTable.SETTINGS.value.name].append(
            {"Name": DynamoDBSettings.EARLIEST_TWEET_DATE})


class TestGenerateTweetBody(TestCase):

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
        """Test that, if one or more previous tweets is not provided or
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
        # Chinese characters are as two by Twitter.
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
