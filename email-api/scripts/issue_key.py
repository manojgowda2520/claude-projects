#!/usr/bin/env python3
"""Mint an API key for a caller.

    python scripts/issue_key.py --tenant alerts \
        --allowed-from alerts@ohteapea.com \
        --description "prod monitoring lambda, account 111111111111"

The raw key is printed exactly once - only its hash is stored. Hand it to the
caller over a channel you trust and have them put it in Secrets Manager or
SSM Parameter Store on their side, not in a plaintext env var.
"""

import argparse
import hashlib
import secrets

import boto3

TABLE = "email-api-keys"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--allowed-from", required=True, nargs="+",
                   help="From addresses this key may use; first is the default")
    p.add_argument("--description", required=True)
    p.add_argument("--max-recipients", type=int, default=50)
    p.add_argument("--region", default="ap-south-1")
    args = p.parse_args()

    raw = f"ok_{args.tenant}_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()

    boto3.resource("dynamodb", region_name=args.region).Table(TABLE).put_item(
        Item={
            "key_hash": key_hash,
            "tenant": args.tenant,
            "allowed_from": args.allowed_from,
            "max_recipients": args.max_recipients,
            "description": args.description,
            "enabled": True,
        },
        ConditionExpression="attribute_not_exists(key_hash)",
    )

    print(f"tenant : {args.tenant}")
    print(f"from   : {', '.join(args.allowed_from)}")
    print(f"key    : {raw}")
    print("\nShown once. Store it now.")


if __name__ == "__main__":
    main()
