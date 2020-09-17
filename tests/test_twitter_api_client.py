from twitter_api_client import TwitterAPIClient
import unittest

"""A test module for twitter_api_client.py."""


class TestTwitterAPIClient(unittest.TestCase):
    """A class for testing TwitterAPIClient."""

    def setUp(self):
        """Set up test data."""
        self.twitter_api = TwitterAPIClient()

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
