"""Admin API for the email service.

Routes (all under /v1/admin, all requiring a key flagged admin=true):

    GET  /v1/admin/keys      list issued keys
    POST /v1/admin/keys      mint a key; the raw value is returned exactly once
    POST /v1/admin/keys/toggle   enable or disable a key by hash
    GET  /v1/admin/activity  recent sends, newest first
    GET  /v1/admin/health    quota, reputation, 24h volume

    GET  /admin              the portal itself (public; the page asks for a key)

The portal HTML is bundled beside this file and read once at cold start.
"""

import datetime as dt
import hashlib
import json
import os
import re
import secrets
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

ddb = boto3.resource("dynamodb")
keys_table = ddb.Table(os.environ["KEYS_TABLE"])
activity_table = ddb.Table(os.environ["ACTIVITY_TABLE"])
cw = boto3.client("cloudwatch")
ses = boto3.client("sesv2")

ROOT_DOMAIN = os.environ["ROOT_DOMAIN"]
# The addresses the mailer's IAM policy permits. Minting a key for anything
# else would produce a key that authenticates but cannot send.
ALLOWED_SENDERS = [a + "@" + ROOT_DOMAIN
                   for a in ("no-reply", "alerts", "billing", "support")]

TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")

with open(os.path.join(os.path.dirname(__file__), "portal.html")) as fh:
    PORTAL_HTML = fh.read()


def _json(status, payload):
    return {"statusCode": status,
            "headers": {"content-type": "application/json",
                        "cache-control": "no-store"},
            "body": json.dumps(payload, default=_coerce)}


def _coerce(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError(type(o))


def _page():
    return {"statusCode": 200,
            "headers": {"content-type": "text/html; charset=utf-8",
                        "cache-control": "no-cache"},
            "body": PORTAL_HTML}


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def list_keys():
    rows = keys_table.scan(ProjectionExpression="key_hash,tenant,allowed_from,"
                                                "enabled,description,max_recipients,"
                                                "created_at,is_admin").get("Items", [])
    for r in rows:
        # Never surface admin keys' hashes to the listing; an admin key that
        # could be revoked from the portal is a lockout waiting to happen.
        if r.get("is_admin"):
            r["key_hash"] = "(admin)"
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return _json(200, {"keys": rows, "allowedSenders": ALLOWED_SENDERS})


def create_key(body):
    tenant = (body.get("tenant") or "").strip().lower()
    from_addr = (body.get("from") or "").strip().lower()
    desc = (body.get("description") or "").strip()

    if not TENANT_RE.match(tenant):
        return _json(400, {"error": "tenant must be 2-31 chars, lowercase letters, digits or hyphen"})
    if from_addr not in ALLOWED_SENDERS:
        return _json(400, {"error": "from must be one of: " + ", ".join(ALLOWED_SENDERS)})
    if not desc:
        return _json(400, {"error": "description is required — say which app this is for"})

    raw = "ok_%s_%s" % (tenant, secrets.token_urlsafe(32))
    key_hash = hashlib.sha256(raw.encode()).hexdigest()

    keys_table.put_item(
        Item={"key_hash": key_hash,
              "tenant": tenant,
              "allowed_from": [from_addr],
              "max_recipients": int(body.get("maxRecipients", 50)),
              "description": desc,
              "enabled": True,
              "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
        ConditionExpression="attribute_not_exists(key_hash)")

    return _json(201, {"key": raw, "keyHash": key_hash, "tenant": tenant,
                       "from": from_addr})


def toggle_key(body):
    key_hash = body.get("keyHash") or ""
    enabled = bool(body.get("enabled"))
    if not re.fullmatch(r"[0-9a-f]{64}", key_hash):
        return _json(400, {"error": "keyHash must be a 64-char hex digest"})

    try:
        r = keys_table.update_item(
            Key={"key_hash": key_hash},
            UpdateExpression="SET enabled = :e",
            ConditionExpression="attribute_exists(key_hash) AND attribute_not_exists(is_admin)",
            ExpressionAttributeValues={":e": enabled},
            ReturnValues="ALL_NEW")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return _json(404, {"error": "no such key, or it is an admin key"})
        raise

    return _json(200, {"key": r["Attributes"],
                       "note": "takes effect within 5 minutes (authorizer cache)"})


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

def activity(qs):
    days = min(int(qs.get("days", 2)), 14)
    limit = min(int(qs.get("limit", 100)), 500)
    tenant = qs.get("tenant")

    today = dt.datetime.now(dt.timezone.utc).date()
    rows = []
    for offset in range(days):
        day = (today - dt.timedelta(days=offset)).isoformat()
        resp = activity_table.query(
            KeyConditionExpression=Key("pk").eq("d#" + day),
            ScanIndexForward=False,
            Limit=limit)
        rows.extend(resp.get("Items", []))
        if len(rows) >= limit:
            break

    if tenant:
        rows = [r for r in rows if r.get("tenant") == tenant]
    return _json(200, {"activity": rows[:limit]})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

_METRICS = [("send", "Send"), ("delivery", "Delivery"),
            ("bounce", "Bounce"), ("complaint", "Complaint")]


def health():
    acct = ses.get_account()
    quota = acct.get("SendQuota", {})

    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(hours=24)

    queries = [{"Id": mid,
                "MetricStat": {"Metric": {"Namespace": "AWS/SES",
                                          "MetricName": name},
                               "Period": 86400,
                               "Stat": "Sum"},
                "ReturnData": True} for mid, name in _METRICS]
    queries += [{"Id": "bouncerate",
                 "MetricStat": {"Metric": {"Namespace": "AWS/SES",
                                           "MetricName": "Reputation.BounceRate"},
                                "Period": 3600, "Stat": "Maximum"}},
                {"Id": "complaintrate",
                 "MetricStat": {"Metric": {"Namespace": "AWS/SES",
                                           "MetricName": "Reputation.ComplaintRate"},
                                "Period": 3600, "Stat": "Maximum"}}]

    data = cw.get_metric_data(MetricDataQueries=queries,
                              StartTime=start, EndTime=now)
    vals = {r["Id"]: (r["Values"][0] if r["Values"] else 0.0)
            for r in data["MetricDataResults"]}

    return _json(200, {
        "quota": {"max24h": quota.get("Max24HourSend"),
                  "sentLast24h": quota.get("SentLast24Hours"),
                  "maxSendRate": quota.get("MaxSendRate")},
        "sendingEnabled": acct.get("SendingEnabled"),
        "productionAccess": acct.get("ProductionAccessEnabled"),
        "last24h": {k: vals.get(k, 0.0) for k, _ in _METRICS},
        "bounceRate": vals.get("bouncerate", 0.0),
        "complaintRate": vals.get("complaintrate", 0.0),
        # SES pauses an account past these; surfaced so the UI can colour them.
        "bounceRateLimit": 0.05,
        "complaintRateLimit": 0.001,
    })


# ---------------------------------------------------------------------------

def handler(event, context):
    path = event["requestContext"]["http"]["path"]
    method = event["requestContext"]["http"]["method"]

    if path.rstrip("/") == "/admin" and method == "GET":
        return _page()

    ctx = (event.get("requestContext", {}).get("authorizer", {}) or {}).get("lambda", {}) or {}
    if ctx.get("is_admin") != "true":
        return _json(403, {"error": "admin key required"})

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            return _json(400, {"error": "invalid JSON"})
    qs = event.get("queryStringParameters") or {}

    route = method + " " + path.rstrip("/")
    if route == "GET /v1/admin/keys":
        return list_keys()
    if route == "POST /v1/admin/keys":
        return create_key(body)
    if route == "POST /v1/admin/keys/toggle":
        return toggle_key(body)
    if route == "GET /v1/admin/activity":
        return activity(qs)
    if route == "GET /v1/admin/health":
        return health()
    return _json(404, {"error": "no such route: " + route})
