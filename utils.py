from datetime import date
from datetime import timedelta
import random

"""This module contains utility methods."""


def random_dates_in_range(start, end, k):
    """Return at most k unique random dates between the given start
    (inclusive) and end (exclusive) dates.

    Args:
        start: A date object.
        end: A date object.
        k: The maximum number of unique random dates to return.

    Returns:
        A list of at most k date objects.

    Raises:
        TypeError: If one or more inputs has an unexpected type.
        ValueError: If end is not greater than start or k < 1.
    """
    if not isinstance(start, date) or not isinstance(end, date):
        raise TypeError(f"One or more dates ({start}, {end}) is not a date.")
    if not isinstance(k, int):
        raise TypeError(f"k {k} is not an integer.")
    if end <= start:
        raise ValueError(f"End {end} must be greater than {start}.")
    if k < 1:
        raise ValueError(f"k {k} is not positive.")
    num_days = (end - start).days
    sample = random.sample(range(num_days), min(num_days, k))
    return [start + timedelta(days=days) for days in sample]


def tweet_url(username, tweet_id):
    """Return the URL to the Tweet with the given ID by the user with
    the given username."""
    return f"https://twitter.com/{username}/statuses/{tweet_id}"
