from http import HTTPStatus
from requests_oauthlib import OAuth1Session
import os
import requests
import settings

"""This module contains methods that act as a thin layer over the
Twitter REST API."""


class TwitterAPIClient(object):

    BASE_URL = "https://api.twitter.com/1.1"

    def __call_api(self, method, url, params={}):
        """Calls the Twitter API with the given method, URL, and
        parameters. Returns the response JSON.

        Args:
            method: An HTTP method as a string (e.g., "GET", "POST")
            url: The URL to make the request to
            params: A dictionary of parameters to provide to the request

        Returns:
            The response in JSON format.

        Raises:
            TwitterAPIError: If the OAuth session cannot be created, the
                             Twitter API fails to return a response with
                             status code 200 OK, or the provided method
                             is invalid.
        """
        session = self.__get_oauth_session()
        try:
            try:
                response = getattr(session, method.lower())(url, params=params)
            except AttributeError:
                raise TwitterAPIError(f"Invalid method {method}.")
            except requests.exceptions.RequestException as e:
                raise TwitterAPIError(e)
            json = response.json()
            if response.status_code != HTTPStatus.OK:
                message = (
                    f"Response has unsuccessful status code "
                    f"{response.status_code}.")
                if "errors" in json and len(json["errors"]) > 0:
                    message = message + " Details:"
                    for error in json["errors"]:
                        if "message" in error:
                            message = f"{message}\n- {error['message']}"
                raise TwitterAPIError(message)
        except TwitterAPIError as e:
            session.close()
            raise e
        session.close()
        return json

    @staticmethod
    def __get_oauth_session():
        """Returns an OAuth session to be used for authorizing requests.
        The session must be closed by the caller.

        Args:
            None.

        Returns:
            An OAuth1Session object.

        Raises:
            TwitterAPIError: If any exception is raised.
        """
        try:
            return OAuth1Session(
                settings.TWITTER_CONSUMER_KEY,
                client_secret=settings.TWITTER_CONSUMER_SECRET,
                resource_owner_key=settings.TWITTER_ACCESS_TOKEN,
                resource_owner_secret=settings.TWITTER_ACCESS_TOKEN_SECRET,
                signature_method=settings.TWITTER_SIGNATURE_METHOD)
        except Exception as e:
            raise TwitterAPIError(e)

    def delete_tweet(self, tweet_id):
        """Deletes the Tweet with the given ID from Twitter.

        Args:
            tweet_id: A string representation of the Tweet ID.

        Returns:
            A Boolean denoting success or failure.

        Raises:
            TwitterAPIError: If the request fails.
        """
        url = os.path.join(self.BASE_URL, f"statuses/destroy/{tweet_id}.json")
        self.__call_api("POST", url)
        return True

    def get_recent_tweets(self, screen_name):
        """Returns recent Tweets tweeted by the user with the given
        screen name from Twitter.

        Args:
            screen_name: A string representation of the user's screen
                         name

        Returns:
            A JSON containing the user's recent tweets.

        Raises:
            TwitterAPIError: If the request fails.
        """
        url = os.path.join(self.BASE_URL, f"statuses/user_timeline.json")
        parameters = {"screen_name": screen_name, "tweet_mode": "extended"}
        json = self.__call_api("GET", url, params=parameters)
        return json

    def post_tweet(self, content):
        """Creates a Tweet on Twitter with the given content.

        Args:
            content: A string containing the text of the Tweet.

        Returns:
            The created Tweet's ID as a string if creation was
            successful, else None.

        Raises:
            TwitterAPIError: If the request fails.
        """
        url = os.path.join(self.BASE_URL, "statuses/update.json")
        parameters = {"status": content}
        json = self.__call_api("POST", url, params=parameters)
        if "id_str" not in json:
            raise TwitterAPIError(f"Response does not contain id_str field.")
        return json["id_str"]

    def tweet_exists(self, tweet_id):
        """Returns whether or not a Tweet with the given ID exists.

        Args:
            tweet_id: A string representation of the Tweet ID.

        Returns:
            A boolean representing whether or not the Tweet exists.

        Raises:
            TwitterAPIError: If the request fails.
        """
        url = os.path.join(self.BASE_URL, "statuses/lookup.json")
        parameters = {"id": tweet_id}
        json = self.__call_api("GET", url, params=parameters)
        return len(json) == 1 and json[0].get("id_str", "") == tweet_id


class TwitterAPIError(Exception):
    """The base class for exceptions in this module."""
    pass
