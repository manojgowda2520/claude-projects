#!/usr/bin/env bash
# Stage each service with the shared modules, ready for terraform to zip.
# Run before `terraform plan` or `terraform apply`.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
build="$here/build"

rm -rf "$build"
for svc in console authorizer mailer otp auth authtriggers; do
  mkdir -p "$build/$svc"
  cp "$root/services/$svc/handler.py" "$build/$svc/"
  # Shared modules are copied in rather than layered, so each bundle is
  # self-contained and a deploy can never mix versions.
  cp "$root"/services/shared/*.py "$build/$svc/"
done

echo "staged:"
find "$build" -type f | sed "s|$build|  build|" | sort
