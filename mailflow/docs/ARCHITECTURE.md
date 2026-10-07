# Mailflow — architecture

Email and managed one-time codes, sold by prepaid credit. Customers sign up on
the landing page, buy credits, generate a key, and call two or three endpoints.

---

## Pricing

**$10 per 10,000 emails.** One credit sends one email; credits never expire.

| Operation | Cost |
|---|---|
| `POST /v1/send` | 1 credit |
| `POST /v1/otp/send` | 1 credit |
| `POST /v1/otp/verify` | free |

Verification is free deliberately. Charging for it pushes customers to cache
codes on their own side, which is the exact problem we are selling them out of.

New accounts are granted 200 credits on first dashboard load.

---

## Two authentication paths, never crossing

```
Browser ──Cognito JWT──▶ /v1/console/*  console λ   account, keys, credits
App     ──x-api-key────▶ /v1/send       mailer λ    send email
                       ▶ /v1/otp/*      otp λ       issue and verify codes
```

A dashboard session cannot send mail. An API key cannot read the account or
mint another key. The account id always comes from the verified JWT or from the
key lookup — never from a request body.

The authorizer deliberately does **not** resolve the credit balance. Its result
is cached for five minutes, and a balance cached that long would let an empty
account keep sending. Balance is enforced at spend time instead.

---

## Credits

One row per account, mutated only through conditional atomic updates:

```
debit:  ADD balance :-1   CONDITION balance >= 1
refund: ADD balance :1
grant:  ADD balance :n    + an append-only ledger row
```

Two concurrent sends against a balance of 1 cannot both succeed — the loser
fails rather than overdrawing. Credits are spent **before** the SES call and
refunded if it fails, so a failure costs nothing and a success is never
double-charged.

The `mf-ledger` table records every credit that *enters* an account (signup
grant, purchase, manual adjustment) and never expires — it is what an invoice or
a dispute is settled from. Spending is not written to the ledger; it is derived
from the balance and the activity log. The mailer and OTP services have no write
access to the ledger at all, so spending can never forge a grant.

---

## Managed OTP

```
POST /v1/otp/send    {email}            -> {requestId, expiresAt}
POST /v1/otp/verify  {requestId, code}  -> {valid: true}
```

The code is never returned to the caller, never logged, and never stored in a
recoverable form. The customer holds only an opaque request id.

**Why HMAC and not a hash.** A six-digit code has a million possibilities; a
plain SHA-256 of one is reversed by brute force in milliseconds. Codes are
stored as `HMAC-SHA256(server_secret, request_id + ":" + code)`. A dumped table
yields nothing without the secret, and mixing in the request id means one stored
digest cannot be replayed against a different request.

Every verification is a constant-time comparison — a byte-wise compare leaks the
code through timing given enough attempts.

**Lifecycle controls:**

| Control | Value | Why |
|---|---|---|
| Attempts | 5, then dead | turns 1-in-a-million into 5-in-a-million |
| Single use | consumed on success | a leaked code cannot be replayed |
| TTL | 10 min default, 1–60 configurable | limits the window |
| Expiry check | on read, not just DynamoDB TTL | TTL deletion lags by minutes |
| Resend cooldown | 60s per recipient | OTP bombing |
| Send window | 3 per recipient per 10 min | OTP bombing |

Recipient addresses in the rate-limit table are hashed, so it holds no readable
contact list worth stealing.

Rotating `OTP_SECRET` invalidates every outstanding code — the correct response
if it is ever suspected of leaking.

---

## Data model

| Table | Key | Notes |
|---|---|---|
| `mf-accounts` | `account_id` | the Cognito `sub`; email, status, brand, reply-to |
| `mf-keys` | `key_hash` | SHA-256 only; GSI `by-account` for listing |
| `mf-credits` | `account_id` | balance, spent, purchased |
| `mf-ledger` | `account_id` + `sk` | append-only, never expires |
| `mf-otp` | `request_id` | HMAC digest, attempts, consumed; TTL |
| `mf-otp-rate` | `account#sha(email)` | send counter; TTL 10 min |
| `mf-idempotency` | `account#key` | TTL 24h |
| `mf-activity` | `acct#<id>#<date>` + `sk` | TTL 30 days, partitioned per account |

Activity is partitioned by account, so one customer's query physically cannot
read another's rows.

---

## Frontend

One file, `web/index.html`. No framework, no build step. It is both the
marketing page and the dashboard — signed out shows the landing page with an
inline auth panel; signed in swaps to the dashboard.

Sign-up and sign-in call the Cognito IDP JSON API directly (`SignUp`,
`ConfirmSignUp`, `InitiateAuth`) rather than redirecting to the hosted UI, which
is what keeps login on the landing page itself. That requires
`ALLOW_USER_PASSWORD_AUTH` on the app client and is safe without a client secret
only over HTTPS — CloudFront enforces it.

Served from a private S3 bucket behind CloudFront at `app.ohteapea.com`.

---

## Known limitations

- **Shared sending domain.** Every customer sends from
  `no-reply@ohteapea.com`, so all of them share one SES reputation and one
  abusive account can pause sending for everybody. Mitigated by per-account SES
  tags for tracing, hard credit limits, and per-account suspension. See
  `RESEND-PARITY.md` — per-customer domain verification is the first real
  upgrade, and it slots in where the mailer resolves `FROM_ADDRESS`.
- **No payment integration.** `POST /v1/console/checkout` returns 501 by design.
  When payments land, the provider's webhook must be the only caller of
  `credits.grant()` — never a route the customer can reach, or they could mint
  credits by replaying a request.
- **No delivery events.** Bounces and complaints reach the SES configuration
  set but are not yet fanned out per account or exposed as webhooks.
- **Cognito's default email sender caps at 50/day**, which will strangle signup
  verification. Switch `email_configuration` to `DEVELOPER` with the SES
  identity before launch.
