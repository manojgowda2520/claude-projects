# Architecture and decisions

This document records *why* the infrastructure looks the way it does. The code
shows what was built; this shows what was rejected.

## Environment isolation

Each environment is a separate Terraform root module with its own state file
under a distinct key in the same S3 bucket (`dev/terraform.tfstate`,
`prod/terraform.tfstate`).

**Rejected: Terraform workspaces.** Workspaces share one backend key and one
provider configuration, so a `terraform destroy` run in the wrong workspace is a
single mistyped command away from deleting production. They also make it awkward
for environments to differ structurally — prod here enables flow logs and runs
two instances, dev runs one. Separate root modules make the difference explicit
and reviewable in `terraform.tfvars`.

**Rejected: one account per environment.** Correct for a real organisation, and
what AWS Control Tower exists to manage. Overkill for a portfolio, and it
doubles the free-tier accounting. The address plan (`10.10.0.0/16` for dev,
`10.20.0.0/16` for prod) is non-overlapping, so environments could be split into
separate accounts or peered later without renumbering.

## Network topology

Two availability zones, two public and two private subnets each.

Public subnets carry an `0.0.0.0/0` route to the internet gateway and set
`map_public_ip_on_launch`. Private subnets have a route table with no default
route unless `enable_nat_gateway` is set.

The private subnets are, by default, unusable for anything that needs to reach
the internet. That is a deliberate trade: a NAT gateway costs roughly USD 32 per
month before data charges, which is more than the rest of this project combined
and outside the free tier entirely. Keeping the subnets in place — correctly
sized, correctly routed, tagged `Tier = private` — means the topology is
production-shaped and one boolean away from being production-correct.

The alternative for reaching AWS APIs without NAT is VPC interface endpoints,
which are also billed hourly. Gateway endpoints for S3 and DynamoDB are free and
would be the first thing added if the workload needed them.

## State backend

S3 with versioning for storage, DynamoDB for locking, both created by
`bootstrap/` which keeps its own state locally.

Versioning on the state bucket is the recovery path when a `terraform apply` is
interrupted mid-write or a state file is corrupted by concurrent access that
somehow escaped the lock. `prevent_destroy` guards both resources: losing state
is materially worse than losing the infrastructure it describes, because
Terraform then has no idea what exists and every resource has to be imported by
hand.

Terraform 1.10 added native S3 locking via `use_lockfile`, which makes the
DynamoDB table optional. It is retained here because DynamoDB locking is what
most existing codebases use and what most teams will ask about.

## Compute access

Instances have no SSH key pair and no inbound port 22. Access is via SSM Session
Manager, granted by attaching `AmazonSSMManagedInstanceCore` to the instance
role.

This removes an entire category of problems: no private keys to distribute,
rotate, or leak; no bastion host to run and patch; no argument about whose IP
should be in the security group. Every session is recorded in CloudTrail with
the IAM identity attached, which is a stronger audit story than shared SSH keys
can offer.

The security-group module enforces this with a `validation` block that fails the
plan if a rule opens port 22 to `0.0.0.0/0`. A guard rail in code catches the
mistake at plan time; a code review catches it only if the reviewer is paying
attention.

## AMI selection

The EC2 module resolves the current Amazon Linux 2023 AMI from SSM Public
Parameters rather than pinning an AMI ID.

Pinned AMI IDs are region-specific and go stale, which means a repository that
worked six months ago fails to plan in a new region. Resolving from SSM always
returns a patched image. The cost is that the AMI ID changes underneath you, so
`lifecycle { ignore_changes = [ami] }` prevents Terraform from proposing to
replace every running instance the moment Amazon publishes an update. Instance
refresh becomes a deliberate act — taint the instance, or move to an autoscaling
group with a launch template, which is the natural evolution of this module.

## CI/CD

Pull requests get static analysis and a plan comment. Merges to `main` apply
`dev`. Production applies are a manual `workflow_dispatch` gated behind a GitHub
environment with required reviewers.

Auto-applying production on merge is a design people put in portfolio projects
to look sophisticated, and it is the wrong default: the review that matters is
of the *plan*, not the diff, because a benign-looking module change can produce a
replacement of every instance. Separating "the code is merged" from "the change
is applied to production" is the whole point of having a plan step.

Scanners run before the plan, not after, so a security finding fails the run
without spending time or AWS API calls on a plan nobody will act on.

## What this would need to be production

- Least-privilege CI role generated from CloudTrail access-advisor data instead
  of AWS managed policies.
- Customer-managed KMS keys for state and EBS, with key policies separating the
  operator role from the CI role.
- An application load balancer and autoscaling group in place of standalone
  instances, so instance replacement is not an outage.
- Automated tests (`terraform test` or Terratest) exercising module contracts,
  particularly the security-group validation logic.
- Drift detection on a schedule, alerting when reality diverges from state.
