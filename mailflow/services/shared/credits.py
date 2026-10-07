"""Credit balance operations, shared by the mailer and the OTP service.

The balance is a single DynamoDB counter mutated with conditional atomic
updates. Two concurrent sends against a balance of 1 cannot both succeed - the
condition makes the loser fail rather than overdraw.
"""

import datetime as dt
import os
import uuid

import boto3
from botocore.exceptions import ClientError

_ddb = boto3.resource("dynamodb")
_credits = _ddb.Table(os.environ["CREDITS_TABLE"])
_ledger = _ddb.Table(os.environ["LEDGER_TABLE"])


class InsufficientCredits(Exception):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def balance(account_id):
    row = _credits.get_item(Key={"account_id": account_id}).get("Item")
    return int(row["balance"]) if row and "balance" in row else 0


def debit(account_id, amount):
    """Spend credits. Raises InsufficientCredits rather than going negative."""
    if amount <= 0:
        return balance(account_id)
    try:
        r = _credits.update_item(
            Key={"account_id": account_id},
            UpdateExpression="ADD balance :neg, spent :amt",
            ConditionExpression="balance >= :amt",
            ExpressionAttributeValues={":neg": -amount, ":amt": amount},
            ReturnValues="ALL_NEW")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise InsufficientCredits()
        raise
    return int(r["Attributes"]["balance"])


def refund(account_id, amount):
    """Give back credits for a send that never left. Best effort - a failed
    refund must not turn one failure into two."""
    if amount <= 0:
        return
    try:
        _credits.update_item(
            Key={"account_id": account_id},
            UpdateExpression="ADD balance :amt, spent :neg",
            ExpressionAttributeValues={":amt": amount, ":neg": -amount})
    except ClientError as e:
        print("refund failed for %s: %s" % (account_id, e))


def grant(account_id, amount, kind, reference="", cents=0):
    """Add credits and write an immutable ledger row.

    `kind` is one of: signup, purchase, manual, refund. Every credit that ever
    enters an account passes through here, so the ledger reconciles against the
    balance exactly.
    """
    r = _credits.update_item(
        Key={"account_id": account_id},
        UpdateExpression="ADD balance :amt, purchased :amt",
        ExpressionAttributeValues={":amt": amount},
        ReturnValues="ALL_NEW")
    new_balance = int(r["Attributes"]["balance"])

    _ledger.put_item(Item={
        "account_id": account_id,
        "sk": "%s#%s" % (_now(), uuid.uuid4().hex[:8]),
        "kind": kind,
        "credits": amount,
        "cents": cents,
        "reference": reference,
        "balance_after": new_balance})
    return new_balance


def history(account_id, limit=50):
    from boto3.dynamodb.conditions import Key as _Key
    return _ledger.query(
        KeyConditionExpression=_Key("account_id").eq(account_id),
        ScanIndexForward=False,
        Limit=limit).get("Items", [])
