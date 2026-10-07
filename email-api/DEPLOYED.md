# What is actually running

**Read this before touching `terraform/`.**

This stack was built by hand from `RUNBOOK.md`, one AWS CLI command at a time.
The Terraform in this repo describes the same architecture but **was never
applied and has no state file**. Running `terraform apply` would try to create a
second copy of everything, and fail partway through on name conflicts — leaving
a mess across a service other teams depend on.

To manage it with Terraform, import the live resources into fresh state first.
Until then, change it the way it was built: with the CLI, following the runbook.

---

## Live resources

Account **975138397215**, region **us-east-1**.

| Resource | Value |
|---|---|
| Endpoint | `https://api.ohteapea.com/v1/send` |
| API Gateway | `qaot7plnoj`, HTTP API, route `POST /v1/send` |
| Custom domain | `api.ohteapea.com`, regional ACM cert, Route 53 alias |
| Lambdas | `email-api-mailer`, `email-api-authorizer` |
| Tables | `email-api-keys`, `email-api-idempotency` (24h TTL) |
| Roles | `email-api-mailer`, `email-api-authorizer` |
| SES config set | `email-api` |
| Sending identity | `ohteapea.com`, DKIM verified, MAIL FROM `mail.ohteapea.com` |
| Allowed senders | `no-reply@`, `alerts@`, `billing@`, `support@` — enforced by the `ses:FromAddress` IAM condition, not by application code |

The SES identity and DNS are **shared** with the OhTeaPea product stack
(`send.ohteapea.com`). Deleting the identity or the DKIM records breaks both.

---

## Two things this stack is missing

**No alarms.** SES pauses an entire account at a 5% bounce or 0.1% complaint
rate. Nothing here warns before that happens, and it would take every sender in
the account down at once — including the product stack.

**One shared key for every team.** It was handed out in a group chat. Access
cannot be revoked for one team without breaking all of them, and the key has
been seen by more people than currently use it. Replacing it with per-team keys
is the first thing worth doing.

The admin portal in `src/admin/` was written to manage keys through a UI but
**was never deployed** — the routes and Lambda do not exist in AWS.

---

## Relationship to the product

`D:\Claude\ohteapea` (GitHub: `manojgowda0704/ohteapea`) is the customer-facing
product on `send.ohteapea.com` and `app.ohteapea.com`. It is a separate stack
with its own Lambdas, tables and Terraform state, and it deploys itself on push.

This repo is the older internal service. The two share only the SES identity and
the DNS zone.
