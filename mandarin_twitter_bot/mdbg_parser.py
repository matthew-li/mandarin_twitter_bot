from bs4 import BeautifulSoup
from http import HTTPStatus
import requests

"""This module contains methods that retrieve and parse information
about Chinese characters from the MDBG Chinese Dictionary:
https://www.mdbg.net/chinese/dictionary."""


class MDBGParser(object):
    """An object that queries mdbg.net's Chinese dictionary.

    It retrieves and stores the pinyin and definitions found for a set
    of simplified Chinese characters.

    Attributes:
        simplified: A string of simplified Chinese characters.
        pinyin: The corresponding pinyin, which may be updated by the
                parser.
        definitions: A list of definitions found by the parser.

    Typical Usage Example:

        mdbg_parser = MDBGParser("你好", pinyin="nǐhǎo")
        entry_found = mdbg_parser.run()
        if entry_found:
            print(mdbg_parser.simplified)
            print(mdbg_parser.pinyin)
            print(mdbg_parser.definitions)
    """

    base_url = "https://www.mdbg.net/chinese/dictionary"

    def __init__(self, simplified, pinyin=None):
        """Initializes the characters, and, optionally, the pinyin.

        Args:
            simplified: A string of simplified Chinese characters.
            pinyin: A string containing the pinyin for the given
                    characters.

        Returns:
            None.

        Raises:
            TypeError: If one or more inputs has an unexpected type.
        """
        if not isinstance(simplified, str):
            raise TypeError(f"Simplified {simplified} is not a string.")
        if pinyin is not None and not isinstance(pinyin, str):
            raise TypeError(f"Pinyin {pinyin} is not a string.")
        self.simplified = simplified
        self.pinyin = pinyin
        self.definitions = []

    def get_search_results(self, search):
        """Returns the response from a lookup for the given search
        phrase.

        Args:
            search: A string comprised of simplified Chinese characters.

        Returns:
            The content of the HTTP response from making a GET request
            for the characters to the online dictionary.

        Raises:
            MDBGError: If the response status code is not 200 OK.
            TypeError: If the search phrase is not a string.
        """
        if not isinstance(search, str):
            raise TypeError(f"Search phrase {search} is not a string.")
        params = {
            "page": "worddict",
            "wdrst": "0",
            "wdqb": search,
        }
        response = requests.get(self.base_url, params=params)
        if response.status_code != HTTPStatus.OK:
            raise MDBGError(
                f"Invalid response status code: {response.status_code}.")
        return response.content

    def run(self):
        """Searches the dictionary for the characters, storing its
        definitions.

        Retrieves HTML from the search results and parses it until the
        characters are found. Sets the parser's pinyin to the result's
        if the two differ. Stores the "/"-separated definitions in a
        list.

        Args:
            None.

        Returns:
            A boolean denoting whether or not a match was found.

        Raises:
            MDBGError: If the response status code is invalid or the
                       response content format is malformed.
        """
        search_results = self.get_search_results(self.simplified)
        soup = BeautifulSoup(search_results, "html.parser")
        table = soup.find("table", {"class": "wordresults"})
        if table is None:
            return False
        tbody = table.find("tbody")
        if tbody is None:
            return False

        simplified_match = False
        for tr in tbody.findAll("tr", {"class": "row"}):
            for div in tr.findAll("div"):
                if not div.get("class"):
                    continue
                try:
                    div_class = div.get("class")[0]
                except IndexError as e:
                    raise MDBGError("Failed to parse page. Details: {e}.")
                if div_class == "hanzi":
                    simplified = ""
                    for span in div.select("span[class*='mpt']"):
                        simplified = simplified + span.text.strip()
                    if simplified == self.simplified:
                        simplified_match = True
                elif div_class == "pinyin":
                    pinyin = ""
                    for span in div.select("span[class*='mpt']"):
                        pinyin = pinyin + span.text.strip()
                    self.pinyin = pinyin
                elif div_class == "defs":
                    self.definitions = [x.strip() for x in div.text.split("/")]
            if simplified_match:
                return True
        return False


class MDBGError(Exception):
    """The base class for exceptions in this module."""
    pass
