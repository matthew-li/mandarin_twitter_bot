import random
import string
import urllib


def generate_nonce(k):
    """Returns a random string of length k consisting of letters and
    digits."""
    choices = string.ascii_letters + string.digits
    return "".join(random.choices(choices, k=k))


def percent_encode(s):
    """Returns a percent-encoded version of the given string."""
    return urllib.parse.quote(s, safe="")
