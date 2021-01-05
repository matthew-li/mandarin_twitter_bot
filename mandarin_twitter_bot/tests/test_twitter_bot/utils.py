from mandarin_twitter_bot.settings import TWITTER_USER_USERNAME
from mandarin_twitter_bot.twitter_api_client import TwitterAPIClient


def delete_created_tweets():
    """Delete created Tweets from Twitter."""
    twitter_api = TwitterAPIClient()
    for tweet in twitter_api.get_recent_tweets(TWITTER_USER_USERNAME):
        tweet_id = tweet["id_str"]
        twitter_api.delete_tweet(tweet_id)
        assert not twitter_api.tweet_exists(tweet_id)
