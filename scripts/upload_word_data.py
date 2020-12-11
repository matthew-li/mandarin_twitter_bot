from ..aws_client import AWSClientError
from ..aws_client import batch_put_items
from ..constants import DynamoDBTable
from ..utils import utc_seconds_since_the_epoch
import argparse
import os
import uuid

"""This script creates entries in the DynamoDB UnprocessedWords table
from an input file.
"""

parser = argparse.ArgumentParser(
    description=(
        "Create entries from the given input file in the DynamoDB "
        "UnprocessedWords table."))
parser.add_argument(
    "input_file", help=(
        "The input file. Each line in the file should be of the form "
        "'word, pinyin'."))


def main():
    args = parser.parse_args()
    input_file = args.input_file
    if not os.path.exists(input_file) or not os.path.isfile(input_file):
        raise ValueError(f"{input_file} is not an existing file.")
    unprocessed_words = []
    with open(input_file) as file:
        for line in file:
            parts = line.split(",")
            if len(parts) != 2:
                print(f"Invalid line: {line}")
                continue
            word = parts[0].strip()
            pinyin = parts[1].strip()
            if not word or not pinyin:
                print(f"Invalid line: {line}")
                continue
            random_id = str(uuid.uuid4())
            unprocessed_word = {
                "Id": random_id,
                "Characters": word,
                "Pinyin": pinyin,
                "InsertionTimestamp": utc_seconds_since_the_epoch(),
            }
            unprocessed_words.append(unprocessed_word)
    try:
        batch_put_items(DynamoDBTable.UNPROCESSED_WORDS, unprocessed_words)
        print("Successfully uploaded word data.")
    except AWSClientError as e:
        print(e)
    except (TypeError, ValueError) as e:
        print(e)


if __name__ == "__main__":
    main()
