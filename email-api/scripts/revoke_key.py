#!/usr/bin/env python3
"""Disable a key by its hash (list the table to find it by description).

    python scripts/revoke_key.py --key-hash <sha256>

Revocation takes effect within the authorizer cache TTL (5 minutes).
"""

import argparse

import boto3


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key-hash", required=True)
    p.add_argument("--region", default="ap-south-1")
    args = p.parse_args()

    boto3.resource("dynamodb", region_name=args.region).Table("email-api-keys").update_item(
        Key={"key_hash": args.key_hash},
        UpdateExpression="SET enabled = :f",
        ExpressionAttributeValues={":f": False},
        ConditionExpression="attribute_exists(key_hash)",
    )
    print("revoked; effective within 5 minutes (authorizer cache TTL)")


if __name__ == "__main__":
    main()
