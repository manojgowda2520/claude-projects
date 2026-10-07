#!/bin/bash
# Cloud-init user data for the application node.
# Keep this idempotent: user data reruns on some replacement paths.
set -euo pipefail

dnf -y update
dnf -y install nginx amazon-cloudwatch-agent

INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
  http://169.254.169.254/latest/api/token)" \
  http://169.254.169.254/latest/meta-data/instance-id)

cat > /usr/share/nginx/html/index.html <<HTML
<!doctype html>
<title>tf-foundation</title>
<h1>Provisioned by Terraform</h1>
<p>Instance: ${INSTANCE_ID}</p>
<p>Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)</p>
HTML

cat > /usr/share/nginx/html/healthz <<HTML
ok
HTML

systemctl enable --now nginx
