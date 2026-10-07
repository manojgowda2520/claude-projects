# Building a Resend-shaped product

What Resend is, what we have, and the path between them.

---

## What actually makes Resend "Resend"

Strip away the marketing and there are six architectural commitments. Everything
else is surface.

1. **Customers send from their own domain.** You add `acme.com`, the product
   returns DNS records, you publish them, it verifies. Mail arrives from
   `hello@acme.com` — your brand, your reputation, your deliverability.
2. **Every message is an object with a lifecycle.** `POST /emails` returns an
   `id`. That email then moves through `queued → sent → delivered → opened →
   clicked`, or `bounced` / `complained`. You can fetch it by id forever.
3. **Events are pushed, not polled.** Webhooks fire on every state change,
   signed so the customer can verify they came from you.
4. **The API is small and obvious.** Six nouns: `emails`, `domains`,
   `api-keys`, `audiences`, `contacts`, `broadcasts`. Flat, REST, no surprises.
5. **DX is the product.** SDKs in seven languages, React Email for templates, a
   dashboard that shows the actual rendered message and its delivery timeline.
6. **Multi-tenancy is real.** Per-account rate limits, per-account suppression
   lists, per-account reputation isolation, dedicated IPs at the top tier.

Points 1 and 2 are the architecture. The rest follows from them.

---

## Where Mailflow stands

| | Mailflow now | Resend-shaped |
|---|---|---|
| Sending domain | one shared address | **per-customer, self-verified** |
| Message identity | SES `MessageId` returned, then forgotten | first-class object, fetchable by id |
| Status | fire and forget | full delivery timeline |
| Events | none | signed webhooks + dashboard timeline |
| API shape | `POST /v1/send` | `POST /emails`, `GET /emails/:id`, `/domains`, `/api-keys` |
| Keys | one kind | scoped: full access vs sending only |
| Rate limits | global 50 rps | per account |
| Suppression | account-wide (SES) | per customer |
| Batch / scheduled / attachments | none | all three |
| SDKs | none | npm + pip at minimum |

The good news: the send path, quota metering, idempotency, and the two-credential
security model all survive unchanged. What changes is what surrounds them.

---

## Target architecture

```
                    ┌──────────────── dashboard (Cognito JWT) ────────────────┐
                    │  domains · api keys · email log · webhooks · usage      │
                    └────────────────────────┬────────────────────────────────┘
                                             │
customer app ──x-api-key──▶ POST /emails ────┤
                                             ▼
                                     ┌───────────────┐
                                     │  emails λ     │
                                     │  · resolve from → owned verified domain
                                     │  · rate limit (per account token bucket)
                                     │  · suppression check (per account)
                                     │  · quota reserve
                                     │  · write email row  status=queued
                                     │  · SES SendEmail, tagged email_id
                                     └───────┬───────┘
                                             │
                     SES config set ─────────▼──────────── SNS ──▶ events λ
                                                                    │
                                              ┌─────────────────────┼──────────────────┐
                                              ▼                     ▼                  ▼
                                      update email status    append timeline     enqueue webhook
                                                                                       │
                                                                            SQS ──▶ webhook λ
                                                                            (HMAC signed, retry, DLQ)
```

### New services

```
services/
  emails/       POST /emails, /emails/batch, GET /emails/:id     (was mailer)
  domains/      POST/GET/DELETE /domains — SES identity lifecycle
  events/       SNS consumer: SES event → email status + timeline
  webhooks/     SQS consumer: signed delivery to customer endpoints, retries
  console/      unchanged in shape, grows domain + log + webhook routes
  authorizer/   unchanged, plus key scope
```

---

## The one hard part: per-customer domains

This is the change that makes everything else worth doing, and it is the only
one with real subtlety.

### Flow

```
POST /domains {"name":"acme.com"}
  → ses.create_email_identity(acme.com, DKIM RSA_2048)
  → ses.put_email_identity_mail_from_attributes(mail.acme.com)
  → store in mf-domains, status=pending
  → return the records for the customer to publish:
        3 × CNAME   <token>._domainkey.acme.com
        1 × MX      mail.acme.com  →  feedback-smtp.<region>.amazonses.com
        1 × TXT     mail.acme.com  →  v=spf1 include:amazonses.com ~all

GET /domains/:id  → ses.get_email_identity → status pending | verified | failed
```

A 5-minute EventBridge rule re-polls pending domains so the dashboard turns
green on its own rather than only when someone refreshes.

### The security consequence

Today the mailer's IAM policy pins `ses:FromAddress` to a fixed list. With
customer domains that list is unbounded, so the policy widens to
`identity/*` and **ownership enforcement moves into application code**:

```python
domain = from_addr.split("@")[1].lower()
row = domains.get_item(Key={"pk": f"{account_id}#{domain}"}).get("Item")
if not row or row["status"] != "verified":
    return 403  # not your domain
```

That check is now the only thing standing between one customer and sending as
another's domain. It needs tests, and the lookup must key on
`account_id + domain` — never on domain alone.

### AWS limits worth knowing before you sell

- **10,000 verified identities** per SES account. Fine for a long time; a hard
  ceiling eventually.
- Verification is asynchronous and depends on the customer's DNS. Expect a
  support load: wrong records, CNAME flattening at Cloudflare, registrars that
  mangle the MAIL FROM MX.
- Sending quota stays **account-wide**. Per-customer rate limits are yours to
  build; SES will not do it for you.

---

## Data model changes

### `mf-domains` — new

| Attribute | Notes |
|---|---|
| `pk` | `<account_id>#<domain>` — ownership is in the key |
| `status` | `pending` · `verified` · `failed` |
| `dkim_tokens` | list, for rendering DNS instructions |
| `mail_from` | `mail.<domain>` |
| `created_at`, `verified_at` | |

### `mf-emails` — new, replaces the fire-and-forget log

| Attribute | Notes |
|---|---|
| `email_id` (PK) | what `POST /emails` returns |
| `account_id`, `ses_message_id` | |
| `status` | `queued` → `sent` → `delivered` / `bounced` / `complained` |
| `timeline` | list of `{status, at}` |
| `to`, `from`, `subject`, `tags` | |
| `expires_at` | 30-day TTL |

GSI `by-account`: `account_id` / `created_at` for the dashboard list.

The `ses_message_id → email_id` mapping is what lets the events consumer find
the right row. Store it as a second GSI rather than scanning.

### `mf-webhooks`, `mf-suppression` — new

Endpoint URL, a signing secret, subscribed event types. Suppression keyed
`<account_id>#<email>` so one customer's bounce list never affects another's.

---

## API surface

Match Resend's shape. Developers already know it, and it costs nothing.

```
POST   /emails              send one           → 200 {"id": "..."}
POST   /emails/batch        up to 100
GET    /emails/:id          status + timeline
POST   /domains             add a domain       → DNS records to publish
GET    /domains             list with status
DELETE /domains/:id
POST   /api-keys            scope: full_access | sending_access
GET    /api-keys
DELETE /api-keys/:id
```

Keep `POST /v1/send` alive as an alias so the internal service keeps working.

---

## Phasing

**Phase 1 — the part that matters** (domains + email objects)
Per-customer domain verification, `mf-domains`, ownership check in the send
path, `mf-emails` with `GET /emails/:id`, API renamed to Resend's shape.
Without this you do not have a product anyone will pay for.

**Phase 2 — the feedback loop**
SES event pipeline into status and timeline, dashboard email log with a real
delivery view, per-account suppression, per-account rate limiting.

**Phase 3 — developer experience**
Signed webhooks with retries, npm and pip SDKs, batch send, attachments,
scheduled send, tags.

**Phase 4 — commercial**
Billing on the metering already in place, teams and members, dedicated IP pools,
audiences and broadcasts.

Phases 1 and 2 are the product. Phase 3 is what makes people choose it. Phase 4
is what makes it a business.

---

## What to reuse as-is

- Cognito auth and the two-credential model
- The atomic conditional-increment quota — it becomes the billing ledger
- Idempotency claim-and-release
- Key hashing, and ownership enforced inside the DynamoDB condition
- Terraform layout, S3 + CloudFront dashboard, the whole build pipeline

Roughly 60% of what exists carries forward. The rewrite is concentrated in the
send path and everything downstream of it.
