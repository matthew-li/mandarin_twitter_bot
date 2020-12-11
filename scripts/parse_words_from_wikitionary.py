import requests
from bs4 import BeautifulSoup
from http import HTTPStatus


"""This script parses simplified Chinese characters and associated
pinyin from https://en.wiktionary.org/wiki/Appendix:Mandarin_Frequency_lists.
"""


WIKTIONARY_API_BASE_URL = "https://en.wiktionary.org/w/api.php"
WIKTIONARY_API_PARAMETERS = {
    "format": "json",
    "action": "parse",
}

WIKTIONARY_PAGE_BASE = "Appendix:Mandarin_Frequency_lists"
WIKTIONARY_PAGE_RANGES = [
    "1-1000",
    "1001-2000",
    "2001-3000",
    "3001-4000",
    "4001-5000",
    "5001-6000",
    "6001-7000",
    "7001-8000",
    "8001-9000",
    "9001-10000",
]
WIKTIONARY_PAGES = [
    f"{WIKTIONARY_PAGE_BASE}/{page_range}" for page_range in [
        "1-1000",
        "1001-2000",
        "2001-3000",
        "3001-4000",
        "4001-5000",
        "5001-6000",
        "6001-7000",
        "7001-8000",
        "8001-9000",
        "9001-10000",
    ]
]


def main():
    for page_range in WIKTIONARY_PAGE_RANGES:
        page = f"{WIKTIONARY_PAGE_BASE}/{page_range}"
        WIKTIONARY_API_PARAMETERS.update({"page": page})
        response = requests.get(
            WIKTIONARY_API_BASE_URL,
            params=WIKTIONARY_API_PARAMETERS)
        assert response.status_code == HTTPStatus.OK

        html = response.json()["parse"]["text"]["*"]
        soup = BeautifulSoup(html)
        with open(f"{page_range}.txt", "w+") as file:
            for tr in soup.findAll("tr"):
                simplified = tr.find("span", {"class": "Hans"})
                pinyin = tr.find("span", {"class": "Latn"})
                if simplified and pinyin:
                    a = simplified.find("a").contents[0].strip()
                    b = pinyin.find("a").contents[0].strip()
                    file.write(f"{a}, {b}\n")


if __name__ == "__main__":
    main()
