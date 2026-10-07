#!/usr/bin/env python3
"""Add credits to an account until payments are wired up.

    python scripts/grant_credits.py --email someone@example.com --credits 10000 \
        --kind purchase --reference "upi ref 4471, $10"

Writes the ledger row alongside the balance change, so the two always
reconcile. Never bump mf-credits directly.
"""

import argparse
import datetime as dt
import os
import uuid

import boto3

os.environ.setdefault("CREDITS_TABLE", "mf-credits")
os.environ.setdefault("LEDGER_TABLE", "mf-ledger")

ddb = boto3.resource("dynamodb")


def find_account(email):
    rows = ddb.Table("mf-accounts").scan(
        FilterExpression="email = :e",
        ExpressionAttributeValues={":e": email}).get("Items", [])
    if not rows:
        raise SystemExit("no account with that email")
    return rows[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--credits", type=int, required=True)
    p.add_argument("--kind", default="manual",
                   choices=["purchase", "manual", "refund", "signup"])
    p.add_argument("--reference", default="")
    p.add_argument("--cents", type=int, default=0, help="what they actually paid")
    args = p.parse_args()

    acct = find_account(args.email)
    account_id = acct["account_id"]

    new_balance = int(ddb.Table("mf-credits").update_item(
        Key={"account_id": account_id},
        UpdateExpression="ADD balance :amt, purchased :amt",
        ExpressionAttributeValues={":amt": args.credits},
        ReturnValues="ALL_NEW")["Attributes"]["balance"])

    ddb.Table("mf-ledger").put_item(Item={
        "account_id": account_id,
        "sk": "%s#%s" % (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                         uuid.uuid4().hex[:8]),
        "kind": args.kind,
        "credits": args.credits,
        "cents": args.cents,
        "reference": args.reference,
        "balance_after": new_balance})

    print("account : %s (%s)" % (args.email, account_id))
    print("granted : %d credits" % args.credits)
    print("balance : %d" % new_balance)


if __name__ == "__main__":
    main()
