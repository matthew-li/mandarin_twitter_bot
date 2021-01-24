import configparser
import os

"""This module contains settings referenced by the application."""


# The format in which dates are stored.
DATE_FORMAT = "%Y-%m-%d"

# Read configuration from a file.
CONFIG_FILE = os.environ["TWITTER_BOT_SETTINGS_MODULE"].strip()
config = configparser.ConfigParser(os.environ)
config.read(CONFIG_FILE)

# AWS-specific settings.
section = "aws"
AWS_DYNAMODB_ENDPOINT_URL = config.get(section, "endpoint_url")
if not AWS_DYNAMODB_ENDPOINT_URL.strip():
    AWS_DYNAMODB_ENDPOINT_URL = None

# Twitter-specific settings.
section = "twitter"
TWITTER_ACCESS_TOKEN = config.get(section, "twitter_access_token")
TWITTER_ACCESS_TOKEN_SECRET = config.get(
    section, "twitter_access_token_secret")
TWITTER_BEARER_TOKEN = config.get(section, "twitter_bearer_token")
TWITTER_CONSUMER_KEY = config.get(section, "twitter_consumer_key")
TWITTER_CONSUMER_SECRET = config.get(section, "twitter_consumer_secret")
TWITTER_SIGNATURE_METHOD = "HMAC-SHA1"
TWITTER_USER_USERNAME = config.get(section, "twitter_user_username")
