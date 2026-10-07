"""API Gateway REQUEST authorizer.

Looks up the SHA-256 of the presented x-api-key in DynamoDB. The raw key is
never stored, so read access to the table does not grant the ability to send.
Returns the key's tenant, From allowlist and admin flag as request context,
which the mailer and admin handlers trust - the caller's own body cannot
influence any of them.
"""

import hashlib
import os

import boto3

_table = boto3.resource("dynamodb").Table(os.environ["KEYS_TABLE"])

DENY = {"isAuthorized": False}


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    presented = headers.get("x-api-key", "")
    if not presented:
        return DENY

    key_hash = hashlib.sha256(presented.encode()).hexdigest()
    item = _table.get_item(Key={"key_hash": key_hash}).get("Item")

    if not item or not item.get("enabled", False):
        # Do not log the key or the hash - a log reader should learn nothing.
        print("auth denied: unknown or disabled key")
        return DENY

    return {
        "isAuthorized": True,
        "context": {
            "tenant": item["tenant"],
            # Comma-joined; API Gateway context values must be strings.
            "allowed_from": ",".join(item.get("allowed_from", [])),
            "max_recipients": str(item.get("max_recipients", 50)),
            "is_admin": "true" if item.get("is_admin") else "false",
        },
    }
