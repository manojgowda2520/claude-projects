# DevOps portfolio — build plan

Goal: three deep, working projects with recruiter-legible repos, wrapped in a
portfolio site. Everything runs on permanently-free infrastructure.

## Accounts and tooling (Manoj does these)

- [ ] AWS account — free tier, 12 months. Needs a card for verification; set a
      $1 billing alarm immediately after signup.
- [ ] Oracle Cloud account — **Always Free** tier, no expiry. This is the
      Kubernetes lab: 4 ARM cores / 24 GB RAM across up to 4 VMs, forever.
- [ ] GitHub — confirm the username on the mgmanoj1481@gmail.com account.
- [ ] `gh` CLI installed locally so repos can be created and pushed from here.

## Project 1 — terraform-aws-foundation ✅ code complete

Multi-env AWS IaC. Modules for VPC / security group / EC2 / S3, isolated dev and
prod state, GitHub Actions with tflint + Trivy + Checkov + PR plan comments,
OIDC instead of stored AWS keys.

Remaining: create the GitHub repo, run `terraform apply` against a real account,
capture plan-comment and Security-tab screenshots for the README.

## Project 2 — devsecops-pipeline (next)

A small containerised service with a full supply-chain pipeline: lint → unit
tests → SAST (Semgrep) → dependency scan → build → image scan (Trivy) → SBOM
(Syft) → sign (cosign) → push to GHCR → deploy to Kubernetes via ArgoCD.
Policy gates with OPA/Conftest. Runs entirely on GitHub Actions and the Oracle
k3s cluster, so it costs nothing.

## Project 3 — k3s-gitops-observability

Bare Oracle ARM VM to running platform, all declarative: Ansible bootstraps the
host (hardening, firewall, k3s), ArgoCD owns everything after that, and the
stack includes Prometheus, Grafana, Loki and Alertmanager. Demonstrates the
"cattle not pets" story end to end.

Differentiator worth adding: an Asterisk exporter dashboard, tying the platform
back to real production VoIP work at Mobil80.

## Project 4 — portfolio site

Static site on GitHub Pages (free, custom domain optional). Projects, skills,
certs, resume download, architecture diagrams. Built last, once there are real
screenshots to show.

## Sequencing note

Code first, cloud second. Every repo can be written, reviewed and committed
before any account exists; the accounts only matter for `apply` and screenshots.
