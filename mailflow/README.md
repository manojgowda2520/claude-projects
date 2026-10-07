# Mailflow

Email and one-time codes as an API. Customers sign up on the landing page, buy
credits, generate a key, and start sending.

**$10 per 10,000 emails.** Credits, not subscriptions. Nothing expires.

```
POST /v1/send        send an email
POST /v1/otp/send    we generate, store and email a code
POST /v1/otp/verify  we verify it — single use, 5 attempts, constant-time
```

## Layout

```
web/index.html            landing page + inline auth + dashboard (one file, no build)
services/
  console/handler.py      dashboard API      (Cognito JWT)
  authorizer/handler.py   key → account      (5 min cache)
  mailer/handler.py       send email         (debits 1 credit)
  otp/handler.py          issue + verify codes
  shared/
    pricing.py            packs, rate, per-operation cost
    credits.py            atomic balance ops + ledger
    otp.py                code generation, HMAC storage, rate limits
infra/terraform/          Cognito · DynamoDB ×7 · Lambda ×4 · HTTP API · S3+CloudFront
docs/ARCHITECTURE.md      data model, OTP security design, limitations
docs/RESEND-PARITY.md     what a Resend-shaped product still needs
```

## Deploy

Needs SES production access, a verified `ohteapea.com` identity, and the
`email-api` configuration set — all of which already exist.

```bash
aws s3 mb s3://mailflow-tfstate-$(aws sts get-caller-identity --query Account --output text)
```

```bash
cd infra/terraform && ./build.sh && terraform init -backend-config="bucket=mailflow-tfstate-$(aws sts get-caller-identity --query Account --output text)" && terraform apply
```

Then open the `dashboard_url` output. Sign up, and 200 free credits land on
first load.

Shipping a frontend change:

```bash
cd infra/terraform && terraform apply -target=aws_s3_object.index && aws cloudfront create-invalidation --distribution-id $(terraform output -raw cloudfront_distribution_id) --paths '/index.html' '/config.js'
```

## Local frontend development

`localhost:8000` is already an allowed Cognito callback and CORS origin:

```bash
cd web && python -m http.server 8000
```

Fill in `web/config.js` from the terraform outputs and you get the deployed
backend behind a local page.

## Security model

Two credentials that never overlap. A dashboard JWT manages the account but
cannot send; an API key sends but cannot read the account. Raw API keys are
never stored — only `sha256(key)` — so a key is revocable but not recoverable.
OTP codes are stored as an HMAC keyed with a server secret, never as a plain
hash, because six digits is trivially brute-forced otherwise.

Read `docs/ARCHITECTURE.md` before changing anything in the credit or OTP paths.

## Granting credits manually

Payments are not wired up; `POST /v1/console/checkout` returns 501 on purpose.
Until then:

```bash
python scripts/grant_credits.py --email someone@example.com --credits 10000 --kind purchase --reference "upi ref 4471, $10" --cents 1000
```

That writes the ledger row alongside the balance change so the two reconcile.
Never bump `mf-credits` directly.
