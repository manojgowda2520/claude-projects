"""Public auth bootstrap. The only unauthenticated route in the product.

    POST /v1/auth/start  {email}  ->  {ok: true}

Ensures a Cognito user exists for that address so the client can immediately
begin a CUSTOM_AUTH challenge. There is no separate sign-up: the first login
creates the account.

Deliberately returns the same response whether the user already existed or was
just created, so this endpoint cannot be used to enumerate customers.
"""

import json
import os
import re
import secrets
import time

import boto3
from botocore.exceptions import ClientError

import otp as otplib

idp = boto3.client("cognito-idp")
rate = boto3.resource("dynamodb").Table(os.environ["OTP_RATE_TABLE"])

POOL_ID = os.environ["USER_POOL_ID"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Tighter than the customer-facing OTP limits: this route can create users.
MAX_STARTS = 5
WINDOW_SECONDS = 900
COOLDOWN_SECONDS = 20


def _json(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps(payload)}


def _rate_ok(email):
    now = int(time.time())
    try:
        rate.update_item(
            Key={"pk": "authstart#" + otplib.recipient_key("_", email)},
            UpdateExpression="ADD sends :one SET last_at = :now, expires_at = :exp",
            ConditionExpression=("attribute_not_exists(pk) OR "
                                 "(sends < :max AND last_at < :cool)"),
            ExpressionAttributeValues={":one": 1, ":now": now,
                                       ":exp": now + WINDOW_SECONDS,
                                       ":max": MAX_STARTS,
                                       ":cool": now - COOLDOWN_SECONDS})
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _ensure_user(email):
    try:
        idp.admin_get_user(UserPoolId=POOL_ID, Username=email)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "UserNotFoundException":
            raise

    idp.admin_create_user(
        UserPoolId=POOL_ID,
        Username=email,
        # Cognito must not send anything - we own delivery.
        MessageAction="SUPPRESS",
        UserAttributes=[{"Name": "email", "Value": email},
                        {"Name": "email_verified", "Value": "true"}])

    # A user created by an admin sits in FORCE_CHANGE_PASSWORD, which blocks
    # CUSTOM_AUTH. Setting a random permanent password moves them to CONFIRMED.
    # Nobody ever learns or uses this value - login is by emailed code only.
    idp.admin_set_user_password(
        UserPoolId=POOL_ID,
        Username=email,
        Password=secrets.token_urlsafe(24) + "Aa1!",
        Permanent=True)


def handler(event, context):
    http = event["requestContext"]["http"]
    if http["method"] + " " + http["path"].rstrip("/") != "POST /v1/auth/start":
        return _json(404, {"error": "no such route"})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})

    email = (body.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return _json(400, {"error": "a valid email is required"})

    if not _rate_ok(email):
        return _json(429, {"error": "too many attempts; wait a minute and try again"})

    try:
        _ensure_user(email)
    except ClientError as e:
        print("ensure_user failed: %s" % e)
        return _json(502, {"error": "could not start sign-in"})

    # Identical response either way - no account enumeration.
    return _json(200, {"ok": True})
