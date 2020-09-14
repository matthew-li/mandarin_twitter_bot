from http import HTTPStatus
from requests_oauthlib import OAuth1Session
import os
import requests
import settings

"""This module contains methods that act as a thin layer over the
Twitter REST API."""


class TwitterAPIClient(object):

    BASE_URL = "https://api.twitter.com/1.1"

    def post_tweet(self, content):
        """Creates a Tweet on Twitter with the given content.

        Args:
            content: A string containing the text of the Tweet.

        Returns:
            The created Tweet's ID as a string if creation was
            successful, else None.

        Raises:
            TwitterAPIError: If the Twitter API fails to return a
                             response or the response's status code is
                             not 200 OK.
        """
        url = os.path.join(self.BASE_URL, "statuses/update.json")
        parameters = {"status": content}
        session = OAuth1Session(
            settings.TWITTER_CONSUMER_KEY,
            client_secret=settings.TWITTER_CONSUMER_SECRET,
            resource_owner_key=settings.TWITTER_ACCESS_TOKEN,
            resource_owner_secret=settings.TWITTER_ACCESS_TOKEN_SECRET,
            signature_method=settings.TWITTER_SIGNATURE_METHOD)
        try:
            response = session.post(url, params=parameters)
        except requests.exceptions.RequestException as e:
            raise TwitterAPIError(
                f"Failed to create Tweet with content {content}. Details: {e}")
        if response.status_code != HTTPStatus.OK:
            raise TwitterAPIError(
                f"Response has unsuccessful status code "
                f"{response.status_code}.")
        json = response.json()
        return json["id_str"]

    def tweet_exists(self, tweet_id):
        """Returns whether or not a Tweet with the given ID exists.

        Args:
            tweet_id: A string representation of the Tweet ID.

        Returns:
            A boolean representing whether or not the Tweet exists.

        Raises:
            TwitterAPIError: If the Twitter API fails to return a
                             response or the response's status code is
                             not 200 OK.
        """
        url = os.path.join(self.BASE_URL, "statuses/lookup.json")
        parameters = {"id": tweet_id}
        session = OAuth1Session(
            settings.TWITTER_CONSUMER_KEY,
            client_secret=settings.TWITTER_CONSUMER_SECRET,
            resource_owner_key=settings.TWITTER_ACCESS_TOKEN,
            resource_owner_secret=settings.TWITTER_ACCESS_TOKEN_SECRET,
            signature_method=settings.TWITTER_SIGNATURE_METHOD)
        try:
            response = session.get(url, params=parameters)
        except requests.exceptions.RequestException as e:
            raise TwitterAPIError(
                f"Failed to retrieve Tweet with ID {tweet_id}. Details: {e}")
        if response.status_code != HTTPStatus.OK:
            raise TwitterAPIError(
                f"Response has unsuccessful status code "
                f"{response.status_code}.")
        json = response.json()
        return len(json) == 1 and json[0]["id_str"] == tweet_id


class TwitterAPIError(Exception):
    """The base class for exceptions in this module."""
    pass
