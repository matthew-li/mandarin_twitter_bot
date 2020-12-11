from collections import namedtuple
from constants import TWEET_MAX_CHARS
from constants import TWEET_URL_LENGTH
from main import generate_tweet_body
from mdbg_parser import MDBGParser
from unittest import TestCase

"""A test module for testing that the method for generating the body of
a Tweet behaves as expected."""


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
