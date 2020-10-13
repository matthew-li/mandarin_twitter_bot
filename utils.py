from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
import random

"""This module contains utility methods."""


def random_dates_in_range(start, end, k):
    """Returns at most k unique random dates between the given start
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
    """Returns the URL to the Tweet with the given ID by the user with
    the given username."""
    return f"https://twitter.com/{username}/statuses/{tweet_id}"


def utc_seconds_since_the_epoch():
    """Returns the number of seconds since the beginning of the epoch.
    UTC time is used.

    Args:
        None.

    Returns:
        A Decimal.

    Raises:
        None.
    """
    epoch_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return Decimal(str((now - epoch_start).total_seconds()))
