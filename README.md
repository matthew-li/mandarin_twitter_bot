# Mandarin Twitter Bot

A Twitter bot [@mandarin_daily](https://twitter.com/mandarin_daily) that tweets Mandarin vocabulary, with links to previous Tweets for reinforcement.

## Overview

Three times a day, the bot tweets a Chinese word, its pinyin, and its definition. In addition, it includes references to previous words tweeted; specifically, it provides URLs to the corresponding tweet from last week, the corresponding tweet from last month, and the corresponding tweet from a random previous date, allowing users to quickly review previously seen words.

The bot is implemented in Python 3.8. It accesses Twitter via the [Twitter API](https://developer.twitter.com/en/docs/twitter-api). Data are stored in [AWS DynamoDB](https://aws.amazon.com/dynamodb/). It runs on [AWS Lambda](https://aws.amazon.com/lambda/), with scheduling handled by [AWS EventBridge](https://aws.amazon.com/eventbridge/). Logs are written to [AWS CloudWatch](https://aws.amazon.com/cloudwatch/).

Words and pinyin are sourced from [Wiktionary](https://en.wiktionary.org/wiki/Appendix:Mandarin_Frequency_lists). Definitions and additional pinyin are scraped from [MDBG's Chinese dictionary](https://www.mdbg.net/chinese/dictionary).

## Configuration
Settings for AWS DynamoDB and Twitter are configured in a configuration file. An example is available at `mandarin_twitter_bot/config/example_config.conf.example`:

```
[aws]
endpoint_url =

[twitter]
twitter_access_token =
twitter_access_token_secret =
twitter_bearer_token =
twitter_consumer_key =
twitter_consumer_secret =
twitter_user_username =
```

The configuration file is selected based on the environment variable `TWITTER_BOT_SETTINGS_MODULE`:
```
export TWITTER_BOT_SETTINGS_MODULE="mandarin_twitter_bot/config/{config_name}_config.conf"
```

## Environments

There are three environments, for production, local staging, and testing.

### Production

The production instance runs on AWS Lambda and DynamoDB.

1. Export production settings.

```
export TWITTER_BOT_SETTINGS_MODULE="mandarin_twitter_bot/config/production_config.conf"
```

2. Create DynamoDB tables.

```
sh mandarin_twitter_bot/deploy/create_tables.sh https://dynamodb.us-west-1.amazonaws.com/
```

3. Zip the source code.

```
sh mandarin_twitter_bot/deploy/zip_code.sh mandarin_twitter_bot
```

4. Zip Pip requirements. Because Lambda has `boto3` pre-installed, it can be removed from `requirements.txt` to save space.

```
sh mandarin_twitter_bot/deploy/zip_pip_requirements.sh mandarin_twitter_bot/requirements.txt
```

5. Create a Lambda function.
    - Set the runtime to Python 3.8.
    - Set the handler to `lambda_function.lambda_handler`.
    - Configure the function to use 128 MB of memory and timeout after 3 minutes.
    - Upload the zipped Pip requirements as a layer.
    - Upload the zipped code.
    - Set the `TWITTER_BOT_SETTINGS_MODULE` environment variable.
    - Add an EventBridge trigger that runs the Lambda function `TWEETS_PER_DAY` times.
        - For example, the cron expression `0 15,19,23 * * ? *` runs the function at 3 p.m., 7 p.m., and 11 p.m. (UTC time) every day.

Note: In production, the bot is instrumented by `lambda_function.py`. On each invocation, the `lambda_handler` makes at most three attempts to run the bot. 

### Staging

A staging instance can be started for manual testing:

0. Install Pip requirements under Python 3.8.

```
pip install -r mandarin_twitter_bot/requirements.txt
```

1. Export staging settings.

```
export TWITTER_BOT_SETTINGS_MODULE="mandarin_twitter_bot/config/staging_config.conf"
```

2. Start a Docker instance of [DynamoDB Local](https://hub.docker.com/r/amazon/dynamodb-local).

```
docker-compose up -f mandarin_twitter_bot/docker-compose.yml
```

3. Create DynamoDB tables. Note that this requires that the [AWS CLI](https://aws.amazon.com/cli/) is installed.

```
sh mandarin_twitter_bot/deploy/create_tables.sh http://localhost:8000
```

### Testing

A testing instance can be started for automated testing:

1. Export test settings.

```
export TWITTER_BOT_SETTINGS_MODULE="mandarin_twitter_bot/config/test_config.conf"
```

2. Start a Docker instance of DynamoDB Local.

```
docker-compose up -f mandarin_twitter_bot/tests/docker-compose.yml
```

3. Create DynamoDB tables.

```
sh mandarin_twitter_bot/deploy/create_tables.sh http://localhost:8001
```

4. Run automated tests.

```
python -m unittest discover mandarin_twitter_bot.tests
```

## Data

The characters chosen are retrieved from Wiktionary's [Mandarin Frequency Lists](https://en.wiktionary.org/wiki/Appendix:Mandarin_Frequency_lists), which includes the 10,000 most frequently used Chinese characters.

1. Parse words from the source. This creates ten files, one for each of the lists.

```
python -m mandarin_twitter_bot.scripts.parse_words_from_wiktionary
```

2. Create an input directory `INPUT_DIR` and move the created files into it. Create an output directory `OUTPUT_DIR`.

3. Clean the words in the input directory, removing duplicates, and write them to a file `words.txt` in `OUTPUT_DIR`.

```
python -m mandarin_twitter_bot.scripts.clean_words INPUT_DIR OUTPUT_DIR
```

4. Randomize the words.

```
sort -R words.txt > randomized.txt
```

5. Upload the word data to the currently configured instance of DynamoDB.

```
python -m mandarin_twitter_bot.scripts.upload_word_data randomized.txt
```
