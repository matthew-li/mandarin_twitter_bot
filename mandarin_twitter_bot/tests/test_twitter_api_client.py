from constants import TWEET_MAX_CHARS
from settings import TWITTER_USER_USERNAME
from twitter_api_client import TwitterAPIClient
from twitter_api_client import TwitterAPIError
import unittest

"""A test module for twitter_api_client.py."""


class TestTwitterAPIClient(unittest.TestCase):
    """A class for testing TwitterAPIClient."""

    def setUp(self):
        """Set up test data."""
        self.twitter_api = TwitterAPIClient()

    def test_delete_tweet_invalid(self):
        """Test that deleting a nonexistent Tweet raises an error."""
        tweet_id = "0000000000000000000"
        try:
            self.twitter_api.delete_tweet(tweet_id)
        except TwitterAPIError as e:
            e = str(e)
            self.assertTrue(
                e.startswith("Response has unsuccessful status code"))
            self.assertIn("No status found with that ID.", e)
        else:
            self.fail("An exception should have been raised.")

    def test_delete_tweet_valid(self):
        """Test that deleting an existent Tweet succeeds."""
        tweet_id = self.twitter_api.post_tweet("This is a test tweet.")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))
        self.assertTrue(self.twitter_api.delete_tweet(tweet_id))
        self.assertFalse(self.twitter_api.tweet_exists(tweet_id))

    def test_get_recent_tweets_invalid(self):
        """Test that retrieving recent Tweets for a user with an invalid
        screen name raises an error."""
        screen_name = "!@#$%^&^%$#@!@#$%^&"
        try:
            self.twitter_api.get_recent_tweets(screen_name)
        except TwitterAPIError as e:
            e = str(e)
            self.assertTrue(
                e.startswith("Response has unsuccessful status code"))
            self.assertIn("Sorry, that page does not exist.", e)
        else:
            self.fail("An exception should have been raised.")

    def test_get_recent_tweets_valid(self):
        """Test that retrieving recent Tweets for a user with a valid
        screen name returns a list of Tweets with extended details in
        the correct order."""
        tweet_1_id = self.twitter_api.post_tweet("Test tweet 1.")
        tweet_2_id = self.twitter_api.post_tweet("Test tweet 2.")
        tweets = self.twitter_api.get_recent_tweets(TWITTER_USER_USERNAME)
        self.assertEqual(len(tweets), 2)
        tweet_2 = tweets[0]
        self.assertEqual(tweet_2["id_str"], tweet_2_id)
        self.assertEqual(tweet_2["full_text"], "Test tweet 2.")
        tweet_1 = tweets[1]
        self.assertEqual(tweet_1["id_str"], tweet_1_id)
        self.assertEqual(tweet_1["full_text"], "Test tweet 1.")
        self.twitter_api.delete_tweet(tweet_1_id)
        self.twitter_api.delete_tweet(tweet_2_id)

    def test_post_tweet_invalid(self):
        """Test that creating a Tweet with too many characters raises an
        error."""
        content = "".join(["." for _ in range(TWEET_MAX_CHARS + 1)])
        try:
            self.twitter_api.post_tweet(content)
        except TwitterAPIError as e:
            e = str(e)
            self.assertTrue(
                e.startswith("Response has unsuccessful status code"))
            self.assertIn("Tweet needs to be a bit shorter.", e)
        else:
            self.fail("An exception should have been raised.")

    def test_post_tweet_valid(self):
        """Test that creating a Tweet succeeds."""
        tweet_id = self.twitter_api.post_tweet("This is a test tweet.")
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))
        self.assertTrue(self.twitter_api.delete_tweet(tweet_id))

    def test_tweet_exists_invalid(self):
        """Test that checking whether a nonexistent Tweet exists returns
        False."""
        tweet_id = "0000000000000000000"
        self.assertFalse(self.twitter_api.tweet_exists(tweet_id))

    def test_tweet_exists_valid(self):
        """Test that checking whether an existent Tweet exists returns
        True."""
        tweet_id = "1288554760430329856"
        self.assertTrue(self.twitter_api.tweet_exists(tweet_id))


if __name__ == "__main__":
    unittest.main()
