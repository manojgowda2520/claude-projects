# email-api

> **This stack was built by hand, not by Terraform.** The `terraform/` directory
> here has never been applied and has no state. Running `terraform apply` would
> try to create a second copy of live resources that other teams depend on.
> Read [DEPLOYED.md](DEPLOYED.md) first.

A shared email-sending API on `https://api.ohteapea.com/v1/send`, backed by SES
in Account A. Anyone holding a valid API key can send — from a Lambda in any
account, an EC2 box, a CI job, or curl. No IAM relationship needed between the
caller's account and Account A.

## Layout

```
terraform/   SES identity + DNS, HTTP API + custom domain, Lambdas, DynamoDB
src/mailer/       POST /v1/send handler
src/authorizer/   API-key lookup (hash → tenant + From allowlist)
scripts/          issue_key.py, revoke_key.py
```

## Deploy

```bash
cd terraform && terraform init && terraform apply
```

Prerequisites: `ohteapea.com` is a Route 53 public hosted zone in Account A,
and SES production access is granted in `var.region` (default `ap-south-1` —
production access is per-region, so this must be the region you were approved
in).

DKIM verification takes a few minutes after apply. Check with:

```bash
aws sesv2 get-email-identity --email-identity ohteapea.com --query VerifiedForSendingStatus
```

## Issue a key

```bash
python scripts/issue_key.py --tenant alerts --allowed-from alerts@ohteapea.com --description "prod monitoring, acct 111111111111"
```

The raw key prints once. Only its SHA-256 is stored, so a table dump does not
let anyone send. Revoke with `scripts/revoke_key.py`; it takes effect within
the 5-minute authorizer cache TTL.

## Send

```bash
curl -sS -X POST https://api.ohteapea.com/v1/send \
  -H "x-api-key: $EMAIL_API_KEY" \
  -H "content-type: application/json" \
  -d '{
        "to": ["ops@example.com"],
        "subject": "Disk usage 91% on prod-db-1",
        "text": "Threshold breached at 14:02 IST.",
        "idempotencyKey": "disk-prod-db-1-2026-09-04T14:02"
      }'
```

### Request fields

| Field | Required | Notes |
|---|---|---|
| `to` | yes | string or array |
| `subject` | yes | unless `template` is used |
| `html` / `text` | one of | both may be supplied |
| `template` / `templateData` | — | SES template, replaces subject/html/text |
| `from` | no | must be in the key's allowlist; defaults to the first entry |
| `cc`, `bcc`, `replyTo` | no | |
| `idempotencyKey` | no | defaults to a hash of the body; dedupes for 24h |

### Responses

| Status | Meaning |
|---|---|
| 202 | accepted, `messageId` returned |
| 200 | duplicate `idempotencyKey`, not re-sent |
| 400 | validation error |
| 401 | `x-api-key` header absent |
| 403 | key unknown, disabled, or not permitted to use that `from` |
| 422 | SES rejected (suppressed address, sending paused) |
| 429 | throttled — retry with backoff |
| 502 | SES error, safe to retry |

## Caller snippet (Python, any account)

```python
import json, os, urllib.request

def send_email(payload):
    req = urllib.request.Request(
        "https://api.ohteapea.com/v1/send",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json",
                 "x-api-key": os.environ["EMAIL_API_KEY"]},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)
```

No SDK, no layer — `urllib` is enough.

## Operational notes

- **Key hygiene.** One key per calling application, never one shared key. The
  tenant tag flows into SES event metrics, so per-app delivery and bounce rates
  are visible in CloudWatch without extra work.
- **Suppression.** Account-level suppression for bounces and complaints is
  enabled, so a hard-bounced address is dropped automatically on later sends.
  Keep the complaint rate under 0.1% or SES pauses the account.
- **DMARC.** Deployed at `p=none`. Watch the aggregate reports for two weeks,
  then move to `p=quarantine` and finally `p=reject`.
- **Throttling** is stage-wide (25 rps default), not per key. If one caller
  starts sending bulk, either give it its own route or put SQS in front of the
  mailer so a SES throttle becomes a retry rather than a caller-visible 429.
- **Attachments** are not supported. Add a `Raw` content branch in the mailer
  if you need them, or — better — send an S3 presigned link.
