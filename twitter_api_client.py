from hashlib import sha1
from utils import generate_nonce, percent_encode
import base64
import hmac
import os
import requests
import settings
import time


class TwitterAPIClient(object):

    BASE_URL = "https://api.twitter.com/1.1"

    @staticmethod
    def _get_authorization_header(url, method, parameters):
        """Returns the Authorization header string needed to authorize
        a request of the given method type with the given URL and
        parameters. This is adapted from the Twitter documentation:

        https://developer.twitter.com/en/docs/basics/authentication/oauth-1-0a/authorizing-a-request

        Args:
            url: The URL being requested.
            method: The HTTP request method.
            parameters: Any parameters to be passed in the URL.

        Returns:
            The header string to be passed to the Authorization header.

        Raises:
            None
        """
        # Generate the parameter string.
        parameters = parameters.copy()
        parameters.update({
            "oauth_consumer_key": settings.TWITTER_CONSUMER_KEY,
            "oauth_nonce": generate_nonce(32),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": settings.TWITTER_ACCESS_TOKEN,
            "oauth_version": "1.0",
        })
        sorted_keys = sorted(parameters.keys())
        parameter_string = percent_encode("&".join(
            [f"{key}={parameters[key]}" for key in sorted_keys]))
        # Generate the signature base string.
        url = percent_encode(url)
        signature_base_string = f"{method}&{url}&{parameter_string}".encode(
            "utf-8")
        # Generate the signing key.
        consumer_secret = percent_encode(settings.TWITTER_CONSUMER_SECRET)
        oauth_token_secret = percent_encode(
            settings.TWITTER_ACCESS_TOKEN_SECRET)
        signing_key = f"{consumer_secret}&{oauth_token_secret}".encode("utf-8")
        # Generate the OAuth signature.
        hashed = hmac.new(signing_key, signature_base_string, sha1)
        encoded = base64.b64encode(hashed.digest())
        oauth_signature = encoded.decode("utf-8")
        # Return the header string.
        header_parameters = parameters.copy()
        header_parameters["oauth_signature"] = oauth_signature
        header = "OAuth "
        for key, value in header_parameters.items():
            key = percent_encode(key)
            value = percent_encode(value)
            header = f"{header}{key}=\"{value}\", "
        return header[:-2]

    def post_tweet(self):
        pass

    def tweet_exists(self, tweet_id):
        """Returns whether or not a Tweet with the given ID exists.

        Args:
            tweet_id: A string representation of the Tweet ID.

        Returns:
            A boolean representing whether or not the Tweet exists.

        Raises:
            TwitterAPIError: If the Twitter API fails to return a
                             response.
        """
        url = os.path.join(self.BASE_URL, "statuses/lookup.json")
        parameters = {"id": tweet_id}
        header = self._get_authorization_header(url, "GET", parameters)
        try:
            response = requests.get(
                url, params=parameters, headers={"Authorization": header})
        except requests.exceptions.RequestException as e:
            raise TwitterAPIError(
                f"Failed to retrieve Tweet with ID {tweet_id}. Details: {e}")
        json = response.json()
        return len(json) == 1 and json[0]["id_str"] == tweet_id


class TwitterAPIError(Exception):
    """The base class for exceptions in this module."""
    pass
