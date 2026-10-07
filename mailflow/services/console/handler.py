"""Customer dashboard API. Every route is behind the Cognito JWT authorizer.

The account id always comes from the verified token, never from the request, so
one customer cannot read or modify another's data whatever they send.
"""

import datetime as dt
import hashlib
import json
import os
import re
import secrets
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import credits as credit_ops
from pricing import PACKS, RATE_CENTS_PER_1000, SIGNUP_GRANT, get_pack

ddb = boto3.resource("dynamodb")
accounts = ddb.Table(os.environ["ACCOUNTS_TABLE"])
keys = ddb.Table(os.environ["KEYS_TABLE"])
activity = ddb.Table(os.environ["ACTIVITY_TABLE"])

NAME_RE = re.compile(r"^[\w .-]{1,40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _json(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps(payload, default=_coerce)}


def _coerce(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(type(o))


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def get_or_create_account(account_id, email):
    """First dashboard load after signup creates the account and grants trial
    credits. The conditional put makes that idempotent across concurrent tabs."""
    row = accounts.get_item(Key={"account_id": account_id}).get("Item")
    if row:
        return row

    row = {"account_id": account_id,
           "email": email,
           "status": "active",
           "reply_to": email,
           "brand": "",
           "created_at": _now()}
    try:
        accounts.put_item(Item=row,
                          ConditionExpression="attribute_not_exists(account_id)")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return accounts.get_item(Key={"account_id": account_id})["Item"]

    credit_ops.grant(account_id, SIGNUP_GRANT, "signup", "welcome credits")
    return row


def me(account_id, email):
    acct = get_or_create_account(account_id, email)
    return _json(200, {
        "account": acct,
        "credits": credit_ops.balance(account_id),
        "packs": PACKS,
        "rateCentsPer1000": RATE_CENTS_PER_1000,
        "endpoints": {
            "send": os.environ["API_BASE"] + "/v1/send",
            "otpSend": os.environ["API_BASE"] + "/v1/otp/send",
            "otpVerify": os.environ["API_BASE"] + "/v1/otp/verify",
        },
        "fromAddress": os.environ["FROM_ADDRESS"],
    })


def update_account(account_id, body):
    updates, values, names = [], {}, {}
    if "replyTo" in body:
        addr = (body.get("replyTo") or "").strip()
        if not EMAIL_RE.match(addr):
            return _json(400, {"error": "not a valid email address"})
        updates.append("reply_to = :r")
        values[":r"] = addr
    if "brand" in body:
        brand = (body.get("brand") or "").strip()[:40]
        updates.append("#b = :b")
        values[":b"] = brand
        names["#b"] = "brand"
    if not updates:
        return _json(400, {"error": "nothing to update"})

    kwargs = {"Key": {"account_id": account_id},
              "UpdateExpression": "SET " + ", ".join(updates),
              "ExpressionAttributeValues": values,
              "ReturnValues": "ALL_NEW"}
    if names:
        kwargs["ExpressionAttributeNames"] = names
    return _json(200, {"account": accounts.update_item(**kwargs)["Attributes"]})


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------

def credits_view(account_id):
    return _json(200, {"credits": credit_ops.balance(account_id),
                       "ledger": credit_ops.history(account_id),
                       "packs": PACKS})


def checkout(account_id, body):
    """Payment is not wired up yet.

    When it is, the provider's webhook is the only thing that should ever call
    credit_ops.grant() - never this route, or a customer could mint credits by
    replaying a request. Returning 501 keeps that boundary honest rather than
    leaving a grant path open in the meantime.
    """
    pack = get_pack(body.get("pack"))
    if not pack:
        return _json(400, {"error": "unknown pack"})
    return _json(501, {
        "error": "checkout not enabled yet",
        "pack": pack,
        "contact": "manoj@" + os.environ.get("ROOT_DOMAIN", "ohteapea.com")})


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def list_keys(account_id):
    rows = keys.query(IndexName="by-account",
                      KeyConditionExpression=Key("account_id").eq(account_id)).get("Items", [])
    for r in rows:
        r.pop("account_id", None)
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return _json(200, {"keys": rows})


def create_key(account_id, body):
    name = (body.get("name") or "").strip()
    if not NAME_RE.match(name):
        return _json(400, {"error": "name must be 1-40 chars (letters, digits, space, . - _)"})

    count = keys.query(IndexName="by-account",
                       KeyConditionExpression=Key("account_id").eq(account_id),
                       Select="COUNT")["Count"]
    if count >= 10:
        return _json(400, {"error": "key limit reached (10); revoke one first"})

    raw = "mf_live_" + secrets.token_urlsafe(32)
    keys.put_item(Item={"key_hash": hashlib.sha256(raw.encode()).hexdigest(),
                        "account_id": account_id,
                        "name": name,
                        "enabled": True,
                        "created_at": _now()},
                  ConditionExpression="attribute_not_exists(key_hash)")
    # The only time the raw key is ever returned.
    return _json(201, {"key": raw, "name": name})


def toggle_key(account_id, body):
    key_hash = body.get("keyHash") or ""
    if not HASH_RE.match(key_hash):
        return _json(400, {"error": "bad keyHash"})
    try:
        row = keys.update_item(
            Key={"key_hash": key_hash},
            UpdateExpression="SET enabled = :e",
            # Ownership lives in the condition, so a hash belonging to someone
            # else fails rather than succeeding silently.
            ConditionExpression="account_id = :a",
            ExpressionAttributeValues={":e": bool(body.get("enabled")), ":a": account_id},
            ReturnValues="ALL_NEW")["Attributes"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _json(404, {"error": "no such key"})
        raise
    row.pop("account_id", None)
    return _json(200, {"key": row, "note": "takes effect within 5 minutes"})


# ---------------------------------------------------------------------------

def recent_activity(account_id, qs):
    days = min(int(qs.get("days", 3)), 14)
    limit = min(int(qs.get("limit", 100)), 300)
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = []
    for offset in range(days):
        day = (today - dt.timedelta(days=offset)).isoformat()
        rows.extend(activity.query(
            KeyConditionExpression=Key("pk").eq("acct#%s#%s" % (account_id, day)),
            ScanIndexForward=False, Limit=limit).get("Items", []))
        if len(rows) >= limit:
            break
    for r in rows:
        r.pop("pk", None)
        r.pop("sk", None)
    return _json(200, {"activity": rows[:limit]})


def handler(event, context):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    account_id = claims["sub"]
    email = claims.get("email", "")

    http = event["requestContext"]["http"]
    route = http["method"] + " " + http["path"].rstrip("/")
    qs = event.get("queryStringParameters") or {}
    try:
        body = json.loads(event["body"]) if event.get("body") else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})

    routes = {
        "GET /v1/console/me": lambda: me(account_id, email),
        "POST /v1/console/account": lambda: update_account(account_id, body),
        "GET /v1/console/credits": lambda: credits_view(account_id),
        "POST /v1/console/checkout": lambda: checkout(account_id, body),
        "GET /v1/console/keys": lambda: list_keys(account_id),
        "POST /v1/console/keys": lambda: create_key(account_id, body),
        "POST /v1/console/keys/toggle": lambda: toggle_key(account_id, body),
        "GET /v1/console/activity": lambda: recent_activity(account_id, qs),
    }
    fn = routes.get(route)
    return fn() if fn else _json(404, {"error": "no such route: " + route})
