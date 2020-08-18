from collections import OrderedDict
import argparse
import os

"""
This script cleans and removes duplicate entries in the files in the
given directory, writing cleaned entries to an output file in the given
directory.
"""

# The name of the file to be written in the output directory.
OUTPUT_FILE = "words.txt"

parser = argparse.ArgumentParser(
    description=(
        "Clean the files in the given input directory and write them "
        "to a single file in the given output directory."))
parser.add_argument(
    "input_dir", help="The input directory containing raw files.")
parser.add_argument(
    "output_dir", help=(
        "The output directory to which a file named words.txt will be "
        "written."))


def main():
    args = parser.parse_args()
    input_dir = args.input_dir
    output_dir = args.output_dir
    for directory in (input_dir, output_dir):
        if not os.path.exists(directory) or not os.path.isdir(directory):
            raise ValueError(f"{directory} is not an existing directory.")
    data = OrderedDict()
    for path, _, files in os.walk(input_dir):
        for file in files:
            with open(os.path.join(path, file)) as input_file:
                for line in input_file:
                    parts = line.split(",")
                    if len(parts) != 2:
                        print(f"Invalid line: {line}")
                        continue
                    word = parts[0].strip()
                    pinyin = parts[1].strip()
                    if not word or not pinyin:
                        print(f"Invalid line: {line}")
                        continue
                    if not pinyin.isalpha():
                        # The pinyin may include the fifth tone; remove any 5s.
                        pinyin = pinyin.replace("5", "")
                        if not pinyin.isalpha():
                            continue
                    if word not in data:
                        data[word] = pinyin
    with open(os.path.join(output_dir, OUTPUT_FILE), "w") as output_file:
        for word, pinyin in data.items():
            output_file.write(f"{word}, {pinyin}\n")


if __name__ == "__main__":
    main()
