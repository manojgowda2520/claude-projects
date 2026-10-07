"""POST /v1/send - send one email through SES.

Auth has already happened in the authorizer; the tenant and the allowed From
addresses arrive as request context and are never read from the request body.
"""

import datetime as dt
import hashlib
import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

ses = boto3.client("sesv2")
_ddb = boto3.resource("dynamodb")
idem_table = _ddb.Table(os.environ["IDEMPOTENCY_TABLE"])
activity_table = _ddb.Table(os.environ["ACTIVITY_TABLE"])

CONFIG_SET = os.environ["CONFIG_SET"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IDEM_TTL_SECONDS = 24 * 60 * 60
ACTIVITY_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_BODY_BYTES = 250 * 1024


def _resp(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(payload)}


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def _record(tenant, from_addr, to, subject, message_id):
    """Best-effort audit row for the admin portal. Never fails a send."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        activity_table.put_item(Item={
            "pk": "d#" + now.date().isoformat(),
            "sk": "%013d#%s" % (int(now.timestamp() * 1000), message_id[-12:]),
            "ts": now.isoformat(timespec="seconds"),
            "tenant": tenant,
            "from": from_addr,
            "to": to[:5],
            "subject": subject or "",
            "message_id": message_id,
            "expires_at": int(time.time()) + ACTIVITY_TTL_SECONDS})
    except Exception as e:  # noqa: BLE001 - auditing must not break delivery
        print("activity write failed: %s" % e)


def handler(event, context):
    ctx = event["requestContext"]["authorizer"]["lambda"]
    tenant = ctx["tenant"]
    allowed_from = ctx["allowed_from"].split(",")
    max_recipients = int(ctx["max_recipients"])
    request_id = event["requestContext"]["requestId"]

    raw = event.get("body") or "{}"
    if len(raw.encode()) > MAX_BODY_BYTES:
        return _resp(413, {"error": "body too large; link large content instead"})
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON"})

    from_addr = body.get("from") or allowed_from[0]
    if from_addr not in allowed_from:
        return _resp(403, {"error": "key not permitted to send as " + from_addr})

    to = _as_list(body.get("to"))
    cc = _as_list(body.get("cc"))
    bcc = _as_list(body.get("bcc"))
    everyone = to + cc + bcc
    if not to:
        return _resp(400, {"error": "to is required"})
    if len(everyone) > max_recipients:
        return _resp(400, {"error": "too many recipients"})
    bad = [a for a in everyone if not EMAIL_RE.match(a)]
    if bad:
        return _resp(400, {"error": "invalid address: " + bad[0]})

    subject = body.get("subject")
    template = body.get("template")
    if not template and not subject:
        return _resp(400, {"error": "subject is required unless using a template"})
    if not template and not (body.get("html") or body.get("text")):
        return _resp(400, {"error": "one of html, text, or template is required"})

    if template:
        content = {"Template": {"TemplateName": template,
                                "TemplateData": json.dumps(body.get("templateData", {}))}}
    else:
        simple = {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": {}}
        if body.get("text"):
            simple["Body"]["Text"] = {"Data": body["text"], "Charset": "UTF-8"}
        if body.get("html"):
            simple["Body"]["Html"] = {"Data": body["html"], "Charset": "UTF-8"}
        content = {"Simple": simple}

    idem = body.get("idempotencyKey") or hashlib.sha256(raw.encode()).hexdigest()
    pk = tenant + "#" + idem
    try:
        idem_table.put_item(
            Item={"pk": pk, "expires_at": int(time.time()) + IDEM_TTL_SECONDS},
            ConditionExpression="attribute_not_exists(pk)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _resp(200, {"status": "duplicate", "idempotencyKey": idem})
        raise

    dest = {}
    if to:
        dest["ToAddresses"] = to
    if cc:
        dest["CcAddresses"] = cc
    if bcc:
        dest["BccAddresses"] = bcc

    kwargs = {"FromEmailAddress": from_addr, "Destination": dest, "Content": content,
              "ConfigurationSetName": CONFIG_SET,
              "EmailTags": [{"Name": "tenant", "Value": tenant}]}
    if body.get("replyTo"):
        kwargs["ReplyToAddresses"] = _as_list(body["replyTo"])

    try:
        result = ses.send_email(**kwargs)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        idem_table.delete_item(Key={"pk": pk})
        if code in ("TooManyRequestsException", "ThrottlingException"):
            return _resp(429, {"error": "rate limited; retry with backoff"})
        if code in ("MessageRejected", "AccountSuspendedException",
                    "SendingPausedException", "MailFromDomainNotVerifiedException"):
            print("rejected req=%s tenant=%s: %s" % (request_id, tenant, e))
            return _resp(422, {"error": str(e)})
        print("send failed req=%s tenant=%s: %s" % (request_id, tenant, e))
        return _resp(502, {"error": "send failed"})

    _record(tenant, from_addr, to, subject, result["MessageId"])
    print("sent req=%s tenant=%s messageId=%s" % (request_id, tenant, result["MessageId"]))
    return _resp(202, {"messageId": result["MessageId"], "idempotencyKey": idem})
