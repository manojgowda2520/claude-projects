# claude-projects

A working archive of side projects and infrastructure work. Each folder stands
alone; nothing here is a monorepo in the build-system sense.

| Folder | What it is |
|---|---|
| `email-api` | Internal email-sending API behind `api.ohteapea.com`. **Live** — see its `DEPLOYED.md` before touching anything. |
| `costlens` | Per-resource AWS cost monitor. Two-tier coverage, Prometheus and Grafana, multi-account via STS. |
| `devops-portfolio` | Terraform AWS foundation module and the roadmap behind it. |
| `seriesforge` | Series generation tooling. |
| `yt-pipeline` | YouTube processing pipeline. |
| `eztrak-deeplinks` | Deep-link handling. |
| `s3-zip`, `scripts` | Small utilities. |
| `mailflow` | **Superseded.** Earlier name for the OhTeaPea product, kept as history. Use the `ohteapea` repo instead. |

## Not in this repo

**`ohteapea`** — the customer-facing email and OTP product on
`send.ohteapea.com` and `app.ohteapea.com`. It lives at
`github.com/manojgowda0704/ohteapea` and deploys itself through GitHub Actions.
Its OIDC trust policy is pinned to that repository's immutable subject claim, so
moving or mirroring it here would stop it deploying. Leave it where it is.

Large material is excluded by `.gitignore`: call recordings, videos and
`yt-prompt-studio`. Those belong in object storage, not version control.

## This repository is public

Nothing here contains credentials — that was checked before the first commit.
It does contain AWS account and resource identifiers, architecture notes and
runbooks. None of that is secret, but it is useful to anyone probing the
accounts, so treat it as published rather than private notes.

Real values live in environment variables and AWS Secrets Manager, never in
these files. `.env`, `*.tfvars` and `*.pem` are ignored to keep it that way.
