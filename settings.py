import configparser
import os


# Dates are stored in the following format.
DATE_FORMAT = "%Y-%m-%d"

# Read configuration from a file.
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.conf")
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

# Twitter-specific settings.
section = "twitter"
TWITTER_ACCESS_TOKEN = config.get(section, "twitter_access_token")
TWITTER_ACCESS_TOKEN_SECRET = config.get(
    section, "twitter_access_token_secret")
TWITTER_CONSUMER_KEY = config.get(section, "twitter_consumer_key")
TWITTER_CONSUMER_SECRET = config.get(section, "twitter_consumer_secret")
TWITTER_USER_ID = config.get(section, "twitter_user_id")
TWITTER_USER_USERNAME = config.get(section, "twitter_user_username")
