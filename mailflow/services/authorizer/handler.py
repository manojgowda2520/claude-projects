"""API-key authorizer for the send and OTP routes.

Deliberately does not resolve the credit balance. Results are cached for five
minutes, and a balance cached that long would let an empty account keep sending.
The balance is enforced at spend time by the conditional debit instead.
"""

import hashlib
import os

import boto3

_ddb = boto3.resource("dynamodb")
keys = _ddb.Table(os.environ["KEYS_TABLE"])
accounts = _ddb.Table(os.environ["ACCOUNTS_TABLE"])

DENY = {"isAuthorized": False}


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    presented = headers.get("x-api-key", "")
    if not presented:
        return DENY

    key_row = keys.get_item(
        Key={"key_hash": hashlib.sha256(presented.encode()).hexdigest()}
    ).get("Item")
    if not key_row or not key_row.get("enabled", False):
        # Never log the key or its hash - a log reader should learn nothing.
        print("denied: unknown or disabled key")
        return DENY

    account_id = key_row["account_id"]
    acct = accounts.get_item(Key={"account_id": account_id}).get("Item")
    if not acct or acct.get("status") != "active":
        print("denied: account %s missing or suspended" % account_id)
        return DENY

    return {
        "isAuthorized": True,
        # Context values must be strings.
        "context": {
            "account_id": account_id,
            "brand": acct.get("brand", ""),
            "reply_to": acct.get("reply_to", ""),
        },
    }
