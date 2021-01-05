from constants import TwitterBotExitCodes
from main import main as run_twitter_bot
import json
import sys
import traceback


def lambda_handler(event, context):
    max_tries = 3
    num_tries = 0
    ok_exit_code = TwitterBotExitCodes.OK
    retry_exit_codes = {
        TwitterBotExitCodes.BAD_DICTIONARY_RESPONSE,
        TwitterBotExitCodes.NO_DICTIONARY_ENTRY,
        TwitterBotExitCodes.TWEET_FAILED,
    }

    success = False
    while num_tries < max_tries:
        num_tries = num_tries + 1
        try:
            run_twitter_bot()
        except SystemExit as e:
            if e.code == ok_exit_code:
                success = True
                break
            elif e.code in retry_exit_codes:
                message = (
                    f"Attempt 1/{max_tries}: Encountered exit code {e.code}. "
                    f"Retrying.")
                sys.stderr.write(message)
            else:
                break
        except Exception as e:
            sys.stderr.write("Uncaught exception. Details:\n")
            traceback.print_exc(file=sys.stderr)
            break
        else:
            sys.stderr.write("A SystemExit should have been raised.")
            break

    if success:
        status_code, body = 200, "OK"
    else:
        status_code, body = 500, "Not OK"

    return {
        "statusCode": status_code,
        "body": json.dumps(body),
    }
