# Handoff — internal email API (`api.ohteapea.com`)

Everything needed to operate, debug or rebuild this service without the
conversation it was built in. This repo is committed locally but **not pushed
anywhere** — copy the whole `email-api` directory to the new machine.

---

## What this is

A shared email-sending API for Mobil80 teams. Any application, in any AWS
account or none, sends mail with one HTTPS call and an API key. No SES access,
IAM role, or SDK required on the caller's side.

It is **separate from and older than** the OhTeaPea product at
`send.ohteapea.com`. Both send through the same SES identity in the same
account, but they are different stacks. Do not repoint one at the other.

---

## Live resources — account 975138397215, us-east-1

| Resource | Identifier |
|---|---|
| Endpoint | `https://api.ohteapea.com/v1/send` |
| API Gateway (HTTP API) | `qaot7plnoj`, route `POST /v1/send`, stage `$default` |
| Custom domain target | `d-vismtwovyi.execute-api.us-east-1.amazonaws.com` |
| API mapping | `lrgdpl` |
| Lambdas | `email-api-mailer`, `email-api-authorizer` |
| IAM roles | `email-api-mailer`, `email-api-authorizer` |
| DynamoDB | `email-api-keys`, `email-api-idempotency` (TTL on `expires_at`) |
| SES config set | `email-api` |
| Route 53 zone | `Z07615811WX71TU6KOQUZ` (`ohteapea.com`) |
| Throttle | 25 rps sustained, 50 burst (stage-wide, not per key) |

Allowed `From` addresses, enforced by an IAM `ses:FromAddress` condition on the
mailer role: `no-reply@`, `alerts@`, `billing@`, `support@` — all
`@ohteapea.com`. Adding a fifth means editing that role policy; minting a key
for an address outside the list succeeds but every send returns 403.

---

## How it was built

**Entirely by hand from CloudShell.** `RUNBOOK.md` is the complete command
history, step by step, with the verification after each one.

`terraform/` describes the same architecture but **was never applied — there is
no state file.** Running `terraform apply` against it today would plan to
create everything from scratch alongside the live resources. To adopt the stack
properly you would have to `terraform import` each resource first. Treat the
directory as reference, not as the deployment mechanism.

---

## Request flow

```
caller ──x-api-key──> api.ohteapea.com (HTTP API)
                            │
                  authorizer Lambda ──> email-api-keys   (sha256 lookup, 5 min cache)
                            │  returns tenant + allowed_from
                      mailer Lambda
                            ├──> email-api-idempotency   (24h dedupe)
                            └──> SES ──> ohteapea.com    (DKIM + SPF via mail.ohteapea.com)
```

Two independent gates on who may send as what: the key row in DynamoDB, and the
IAM condition underneath it. Tampering with the table alone cannot widen access.

The authorizer caches for 5 minutes, so a revoked key stays usable for up to
that long.

---

## Status codes

| Code | Meaning |
|---|---|
| 202 | accepted, `messageId` returned |
| 200 | duplicate `idempotencyKey` — not re-sent |
| 400 | validation error |
| 401 | `x-api-key` header absent (rejected before the authorizer runs) |
| 403 | key unknown, disabled, or not allowed that `from` |
| 422 | SES rejected — usually a suppressed address |
| 429 | throttled |
| 502 | SES error, safe to retry |

---

## Operating it

All of these run from CloudShell in account 975138397215.

### Mint a key

```bash
T=billing; F=billing@ohteapea.com; D="invoicing service"
K="ok_${T}_$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
H=$(printf '%s' "$K" | sha256sum | cut -d' ' -f1)
aws dynamodb put-item --table-name email-api-keys --item "{\"key_hash\":{\"S\":\"$H\"},\"tenant\":{\"S\":\"$T\"},\"allowed_from\":{\"L\":[{\"S\":\"$F\"}]},\"max_recipients\":{\"N\":\"50\"},\"enabled\":{\"BOOL\":true},\"description\":{\"S\":\"$D\"}}" --condition-expression "attribute_not_exists(key_hash)"
printf "\nKEY : %s\nhash: %s\n" "$K" "$H"
```

Record the **hash**, not the key. Only the hash is stored, so a key can be
revoked but never recovered.

### List keys

```bash
aws dynamodb scan --table-name email-api-keys --query "Items[].{Tenant:tenant.S,From:allowed_from.L[0].S,Enabled:enabled.BOOL,Hash:key_hash.S,Desc:description.S}" --output table
```

### Revoke

```bash
aws dynamodb update-item --table-name email-api-keys --key '{"key_hash":{"S":"PASTE_HASH"}}' --update-expression "SET enabled = :f" --expression-attribute-values '{":f":{"BOOL":false}}'
```

Effective within the 5-minute authorizer cache.

### Update a Lambda after editing a handler

```bash
cd src/mailer && zip -q /tmp/m.zip handler.py && aws lambda update-function-code --function-name email-api-mailer --zip-file fileb:///tmp/m.zip
```

### Logs

```bash
aws logs tail /aws/lambda/email-api-mailer --since 15m --follow
aws logs tail /aws/lambda/email-api-authorizer --since 15m
```

---

## Known gaps

**No CloudWatch alarms.** SES pauses the entire account at a 5% bounce rate or
0.1% complaint rate — which would also take down OhTeaPea, since both use the
same SES identity. Nothing currently warns before that happens. The fix:

```bash
aws cloudwatch put-metric-alarm --alarm-name ses-bounce-rate --namespace AWS/SES --metric-name Reputation.BounceRate --statistic Average --period 900 --evaluation-periods 1 --threshold 0.03 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching
aws cloudwatch put-metric-alarm --alarm-name ses-complaint-rate --namespace AWS/SES --metric-name Reputation.ComplaintRate --statistic Average --period 900 --evaluation-periods 1 --threshold 0.001 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching
```

Attach an SNS topic with `--alarm-actions` or they alarm silently.

**One shared key across all teams.** `ok_shared_…`, tenant `shared`, sending as
`no-reply@`. It cannot be revoked for one team without breaking every team, and
CloudWatch attributes all traffic to a single tenant so there is no per-app
visibility. Migrating means minting per-team keys and retiring the shared one.

**That shared key has been distributed over WhatsApp** and appears in a Claude
transcript. It should be rotated: mint a replacement, distribute it, then
disable the old hash.

**No attachment support.** The handler sends `Simple` content only. Attachments
need a `Raw` MIME branch, or — better — an S3 presigned link in the body.

**Not in version control anywhere.** One local commit, no remote.

---

## Files

| Path | What |
|---|---|
| `RUNBOOK.md` | the full CloudShell build, step by step |
| `INTEGRATION.md` | the doc given to consuming teams |
| `README.md` | architecture and request/response reference |
| `src/mailer/handler.py` | validation, idempotency, SES send |
| `src/authorizer/handler.py` | key hash lookup → tenant + allowed senders |
| `src/admin/` | admin handler and portal page |
| `scripts/` | `issue_key.py`, `revoke_key.py` |
| `terraform/` | reference only — never applied, no state |
