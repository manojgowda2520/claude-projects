# Sending email — integration guide

Send email from any application, in any AWS account or none, with one HTTPS
call. You do not need SES access, an IAM role, a VPC change, or an SDK.

**Endpoint:** `POST https://api.ohteapea.com/v1/send`
**Auth:** `x-api-key` header

Ask the platform team for a key. Each key is scoped to one application and to
the `From` address that application sends as.

---

## Quickstart

```bash
curl -X POST https://api.ohteapea.com/v1/send \
  -H "x-api-key: $EMAIL_API_KEY" \
  -H "content-type: application/json" \
  -d '{"to":["user@example.com"],"subject":"Your invoice","text":"Attached below."}'
```

That is the whole thing. Three fields.

---

## Request

| Field | Type | Required | Notes |
|---|---|---|---|
| `to` | string or array | **yes** | recipient(s) |
| `subject` | string | **yes** | |
| `text` | string | one of | plain-text body |
| `html` | string | one of | HTML body; send both for best client support |
| `cc` | string or array | no | |
| `bcc` | string or array | no | |
| `replyTo` | string | no | where replies go — often a real inbox |
| `from` | string | no | must be allowed for your key; defaults to your key's address |
| `idempotencyKey` | string | no | see below — use it |

You do not normally pass `from`. Your key already determines it.

## Response

`202 Accepted`

```json
{"messageId": "010001a06b0639f9-...", "idempotencyKey": "invoice-8891"}
```

A 202 means SES accepted the message for delivery, not that it reached the
inbox. Delivery is asynchronous.

| Status | Meaning | What to do |
|---|---|---|
| 202 | accepted | done |
| 200 | duplicate `idempotencyKey` — not re-sent | treat as success |
| 400 | bad request (missing field, malformed address) | fix the payload; do not retry |
| 401 | no `x-api-key` header | fix your config |
| 403 | key unknown, disabled, or not allowed to use that `from` | contact platform team |
| 422 | SES rejected — usually a suppressed address | do not retry; the recipient bounced or complained previously |
| 429 | rate limited | retry with exponential backoff |
| 502 | transient SES error | safe to retry |

Retry on 429 and 502 only. Everything else is permanent.

---

## Idempotency — please use it

Pass an `idempotencyKey` that is unique to the *event*, not to the attempt:

```json
{"idempotencyKey": "invoice-8891-reminder-2"}
```

If your process times out and retries, the second call returns `200
{"status":"duplicate"}` and sends nothing. Without a key, we hash the request
body — which still dedupes identical retries, but two genuinely different
sends with identical content would collide. An explicit key is always better.

Keys are remembered for 24 hours.

---

## Code

### Python (any runtime — no dependencies)

```python
import json, os, urllib.error, urllib.request

ENDPOINT = "https://api.ohteapea.com/v1/send"

def send_email(to, subject, text=None, html=None, idempotency_key=None):
    payload = {"to": to if isinstance(to, list) else [to], "subject": subject}
    if text:
        payload["text"] = text
    if html:
        payload["html"] = html
    if idempotency_key:
        payload["idempotencyKey"] = idempotency_key

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json",
                 "x-api-key": os.environ["EMAIL_API_KEY"]},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 429 and 502 are worth retrying; the rest are not.
        raise RuntimeError(f"email api {e.code}: {e.read().decode()}") from e
```

### Node 18+

```javascript
const ENDPOINT = "https://api.ohteapea.com/v1/send";

export async function sendEmail(payload) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": process.env.EMAIL_API_KEY,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`email api ${res.status}: ${await res.text()}`);
  return res.json();
}
```

---

## Templating

Render your HTML in your own application, in whatever templating engine you
already use, and pass the result as `html`. Your email copy then lives in your
repo, versioned and reviewed alongside the code that sends it — no ticket to
the platform team to change a subject line.

Always send `text` alongside `html`. Some clients prefer it, and its presence
improves deliverability.

---

## Handling your key

- Store it in Secrets Manager or SSM Parameter Store. Never in a repo, never in
  a plaintext environment variable in source control.
- One key per application. Do not share one key across services — a shared key
  cannot be revoked without breaking everything at once.
- Rotate by requesting a new key, deploying it, then asking for the old one to
  be disabled.
- If a key leaks, tell the platform team immediately. Revocation takes effect
  within five minutes.

Keys are stored only as hashes. Nobody, including the platform team, can read
your key back to you — a lost key is replaced, not recovered.

---

## Rate limits

The API accepts 25 requests/second sustained across all callers, bursting to
50. Underneath, SES allows 14 messages/second and 50,000 per day for the whole
organisation.

If you need to send in bulk — thousands of messages in a batch — talk to the
platform team first rather than looping over this endpoint. We will queue it
properly instead of letting you exhaust everyone's quota.

---

## Deliverability

Messages are DKIM-signed and SPF-aligned for `ohteapea.com`, so they
authenticate correctly at the receiving end. What still lands you in spam is
content and behaviour:

- Send to people who expect it. Complaints damage the reputation of the whole
  domain, for every team.
- A hard-bounced address is suppressed automatically. Repeatedly sending to
  addresses that bounce is the fastest way to get everyone's sending paused.
- Keep an unsubscribe path in anything that is not strictly transactional.

---

## Support

Contact the platform team with your tenant name and the `messageId` from the
response — that is enough to trace any individual message end to end.
