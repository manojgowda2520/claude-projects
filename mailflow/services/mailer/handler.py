"""POST /v1/send - the general-purpose send endpoint.

    validate -> claim idempotency -> debit credit -> send -> record

The credit is spent before the SES call and refunded if the send fails, so a
failure costs the customer nothing and a success can never be double-charged.
"""

import datetime as dt
import hashlib
import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

from credits import InsufficientCredits, debit, refund
from pricing import COST

ses = boto3.client("sesv2")
_ddb = boto3.resource("dynamodb")
idem = _ddb.Table(os.environ["IDEMPOTENCY_TABLE"])
activity = _ddb.Table(os.environ["ACTIVITY_TABLE"])

FROM_ADDRESS = os.environ["FROM_ADDRESS"]
CONFIG_SET = os.environ["CONFIG_SET"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IDEM_TTL = 24 * 60 * 60
ACTIVITY_TTL = 30 * 24 * 60 * 60
MAX_BODY_BYTES = 250 * 1024
MAX_RECIPIENTS = 50


def _resp(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(payload)}


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def _record(account_id, to, subject, message_id, kind="send"):
    """Best-effort audit row. Never fails a send."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        activity.put_item(Item={
            "pk": "acct#%s#%s" % (account_id, now.date().isoformat()),
            "sk": "%013d#%s" % (int(now.timestamp() * 1000), message_id[-12:]),
            "ts": now.isoformat(timespec="seconds"),
            "kind": kind,
            "to": to[:5],
            "subject": subject or "",
            "message_id": message_id,
            "expires_at": int(time.time()) + ACTIVITY_TTL})
    except Exception as e:  # noqa: BLE001 - auditing must not break delivery
        print("activity write failed: %s" % e)


def handler(event, context):
    ctx = event["requestContext"]["authorizer"]["lambda"]
    account_id = ctx["account_id"]
    request_id = event["requestContext"]["requestId"]

    raw = event.get("body") or "{}"
    if len(raw.encode()) > MAX_BODY_BYTES:
        return _resp(413, {"error": "body too large; link large content instead"})
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON"})

    to = _as_list(body.get("to"))
    cc = _as_list(body.get("cc"))
    bcc = _as_list(body.get("bcc"))
    everyone = to + cc + bcc
    if not to:
        return _resp(400, {"error": "to is required"})
    if len(everyone) > MAX_RECIPIENTS:
        return _resp(400, {"error": "too many recipients (max %d)" % MAX_RECIPIENTS})
    bad = [a for a in everyone if not EMAIL_RE.match(a)]
    if bad:
        return _resp(400, {"error": "invalid address: " + bad[0]})

    subject = body.get("subject")
    if not subject:
        return _resp(400, {"error": "subject is required"})
    html, text = body.get("html"), body.get("text")
    if not (html or text):
        return _resp(400, {"error": "one of html or text is required"})

    # --- idempotency -------------------------------------------------------
    key = body.get("idempotencyKey") or hashlib.sha256(raw.encode()).hexdigest()
    pk = account_id + "#" + key
    try:
        idem.put_item(Item={"pk": pk, "expires_at": int(time.time()) + IDEM_TTL},
                      ConditionExpression="attribute_not_exists(pk)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _resp(200, {"status": "duplicate", "idempotencyKey": key})
        raise

    # --- credits -----------------------------------------------------------
    cost = COST["send"] * max(1, len(everyone) // MAX_RECIPIENTS + (1 if len(everyone) % MAX_RECIPIENTS else 0))
    try:
        remaining = debit(account_id, cost)
    except InsufficientCredits:
        idem.delete_item(Key={"pk": pk})
        return _resp(402, {"error": "out of credits",
                           "topUp": "https://ohteapea.com/#pricing"})

    # --- send --------------------------------------------------------------
    dest = {"ToAddresses": to}
    if cc:
        dest["CcAddresses"] = cc
    if bcc:
        dest["BccAddresses"] = bcc

    simple = {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": {}}
    if text:
        simple["Body"]["Text"] = {"Data": text, "Charset": "UTF-8"}
    if html:
        simple["Body"]["Html"] = {"Data": html, "Charset": "UTF-8"}

    kwargs = {"FromEmailAddress": FROM_ADDRESS,
              "Destination": dest,
              "Content": {"Simple": simple},
              "ConfigurationSetName": CONFIG_SET,
              # Tagged per account so one customer's reputation can be traced
              # and cut off without touching the others.
              "EmailTags": [{"Name": "account", "Value": account_id[:64]},
                            {"Name": "kind", "Value": "send"}]}

    reply_to = body.get("replyTo") or ctx.get("reply_to")
    if reply_to:
        kwargs["ReplyToAddresses"] = _as_list(reply_to)

    try:
        result = ses.send_email(**kwargs)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        idem.delete_item(Key={"pk": pk})
        refund(account_id, cost)
        if code in ("TooManyRequestsException", "ThrottlingException"):
            return _resp(429, {"error": "rate limited; retry with backoff"})
        if code in ("MessageRejected", "AccountSuspendedException",
                    "SendingPausedException", "MailFromDomainNotVerifiedException"):
            print("rejected req=%s acct=%s: %s" % (request_id, account_id, e))
            return _resp(422, {"error": str(e)})
        print("send failed req=%s acct=%s: %s" % (request_id, account_id, e))
        return _resp(502, {"error": "send failed"})

    _record(account_id, to, subject, result["MessageId"])
    print("sent req=%s acct=%s id=%s" % (request_id, account_id, result["MessageId"]))
    return _resp(202, {"messageId": result["MessageId"],
                       "idempotencyKey": key,
                       "creditsRemaining": remaining})
