"""Managed OTP: we generate the code, email it, and verify it.

    POST /v1/otp/send    {email}            -> {requestId, expiresAt}
    POST /v1/otp/verify  {requestId, code}  -> {valid}

The code is never returned to the caller, never logged, and never stored in a
recoverable form. The customer holds only an opaque request id.
"""

import datetime as dt
import json
import os
import re
import time
import uuid

import boto3
from botocore.exceptions import ClientError

import otp as otplib
from credits import InsufficientCredits, debit, refund
from pricing import COST

ses = boto3.client("sesv2")
_ddb = boto3.resource("dynamodb")
codes = _ddb.Table(os.environ["OTP_TABLE"])
rate = _ddb.Table(os.environ["OTP_RATE_TABLE"])

FROM_ADDRESS = os.environ["FROM_ADDRESS"]
CONFIG_SET = os.environ["CONFIG_SET"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _resp(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps(payload)}


def _rate_ok(account_id, email):
    """One conditional write enforces both the cooldown and the window cap."""
    now = int(time.time())
    try:
        rate.update_item(
            Key={"pk": otplib.recipient_key(account_id, email)},
            UpdateExpression="ADD sends :one SET last_at = :now, expires_at = :exp",
            ConditionExpression=(
                "attribute_not_exists(pk) OR "
                "(sends < :max AND last_at < :cooldown)"),
            ExpressionAttributeValues={
                ":one": 1,
                ":now": now,
                ":exp": now + otplib.RATE_WINDOW_SECONDS,
                ":max": otplib.MAX_SENDS_PER_WINDOW,
                ":cooldown": now - otplib.RESEND_COOLDOWN_SECONDS})
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def send(account_id, body, brand):
    email = (body.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        return _resp(400, {"error": "a valid email is required"})

    ttl = otplib.clamp_ttl(body.get("ttlSeconds", otplib.DEFAULT_TTL_SECONDS))
    length = body.get("length", otplib.DEFAULT_LENGTH)

    if not _rate_ok(account_id, email):
        return _resp(429, {
            "error": "too many codes requested for this address",
            "retryAfter": otplib.RESEND_COOLDOWN_SECONDS,
            "detail": "at most %d codes per %d minutes, %ds between sends" % (
                otplib.MAX_SENDS_PER_WINDOW,
                otplib.RATE_WINDOW_SECONDS // 60,
                otplib.RESEND_COOLDOWN_SECONDS)})

    try:
        remaining = debit(account_id, COST["otp_send"])
    except InsufficientCredits:
        return _resp(402, {"error": "out of credits",
                           "topUp": "https://ohteapea.com/#pricing"})

    request_id = uuid.uuid4().hex
    code = otplib.generate_code(length)
    expires = int(time.time()) + ttl

    codes.put_item(Item={
        "request_id": request_id,
        "account_id": account_id,
        "code_digest": otplib.digest(request_id, code),
        "attempts": 0,
        "consumed": False,
        "created_at": int(time.time()),
        # DynamoDB TTL is the backstop; expiry is enforced on read regardless,
        # because TTL deletion can lag by minutes.
        "expires_at": expires})

    subject, html, text = otplib.render(code, ttl, brand)
    try:
        ses.send_email(
            FromEmailAddress=FROM_ADDRESS,
            Destination={"ToAddresses": [email]},
            Content={"Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"},
                         "Text": {"Data": text, "Charset": "UTF-8"}}}},
            ConfigurationSetName=CONFIG_SET,
            EmailTags=[{"Name": "account", "Value": account_id[:64]},
                       {"Name": "kind", "Value": "otp"}])
    except ClientError as e:
        refund(account_id, COST["otp_send"])
        codes.delete_item(Key={"request_id": request_id})
        code = None  # noqa: F841 - drop the reference promptly
        print("otp send failed acct=%s: %s" % (account_id, e))
        if e.response["Error"]["Code"] in ("TooManyRequestsException", "ThrottlingException"):
            return _resp(429, {"error": "rate limited; retry with backoff"})
        return _resp(502, {"error": "could not send code"})

    return _resp(202, {
        "requestId": request_id,
        "expiresAt": dt.datetime.fromtimestamp(expires, dt.timezone.utc)
                       .isoformat(timespec="seconds"),
        "creditsRemaining": remaining})


def verify(account_id, body):
    request_id = (body.get("requestId") or "").strip()
    code = (body.get("code") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{32}", request_id) or not code.isdigit():
        return _resp(400, {"error": "requestId and numeric code are required"})

    item = codes.get_item(Key={"request_id": request_id}).get("Item")
    # A code belonging to another account is treated as absent, not as a
    # permission error - it should be indistinguishable from a bad id.
    if not item or item.get("account_id") != account_id:
        return _resp(404, {"error": "unknown or expired request"})

    if item.get("consumed"):
        return _resp(410, {"error": "code already used"})
    if int(item["expires_at"]) <= int(time.time()):
        return _resp(410, {"error": "code expired"})

    try:
        item = codes.update_item(
            Key={"request_id": request_id},
            UpdateExpression="ADD attempts :one",
            ConditionExpression="attempts < :max AND consumed = :f",
            ExpressionAttributeValues={":one": 1,
                                       ":max": otplib.MAX_ATTEMPTS,
                                       ":f": False},
            ReturnValues="ALL_NEW")["Attributes"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _resp(429, {"error": "too many attempts; request a new code"})
        raise

    if not otplib.matches(request_id, code, item["code_digest"]):
        left = otplib.MAX_ATTEMPTS - int(item["attempts"])
        return _resp(200, {"valid": False, "attemptsRemaining": max(0, left)})

    # Single use: consume it so a leaked code cannot be replayed.
    codes.update_item(
        Key={"request_id": request_id},
        UpdateExpression="SET consumed = :t REMOVE code_digest",
        ExpressionAttributeValues={":t": True})
    return _resp(200, {"valid": True})


def handler(event, context):
    ctx = event["requestContext"]["authorizer"]["lambda"]
    account_id = ctx["account_id"]
    brand = ctx.get("brand") or ""

    http = event["requestContext"]["http"]
    route = http["method"] + " " + http["path"].rstrip("/")
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON"})

    if route == "POST /v1/otp/send":
        return send(account_id, body, brand)
    if route == "POST /v1/otp/verify":
        return verify(account_id, body)
    return _resp(404, {"error": "no such route"})
