#!/usr/bin/env bash
# Common Cloud Run deploy helpers shared by ci-workflows reusable workflows
# (currently `secret-verify-gcp.yml`'s `repo_type: cloud-run` path).
#
# Why this exists: cloud-run-deploy.yml callers declare the GCP secret
# bindings inline via `with: update_secrets: ENV=SECRET[:VER],...`. The
# verify reusable needs to extract those same names so the two stay in
# sync from a single source. Both workflows shell out to this script so
# the parsing logic lives in exactly one place.
#
# Currently supported subcommands:
#   extract-secrets <workflow-yaml>
#     Parse `update_secrets` / `set_secrets` from every job's `with:`
#     block in the given workflow file. Emit one GCP Secret Manager name
#     per line, sorted unique. GitHub Actions expressions (`${{ ... }}`)
#     in the secret name slot are skipped with a warning.
#
# Local usage (debugging):
#   bash scripts/cloud-run/deploy.sh extract-secrets ../my-repo/.github/workflows/ci.yml
#
# Exit codes:
#   0  - success
#   1  - runtime error (file not found, parse failure, etc.)
#   2  - usage error (unknown subcommand, missing args)

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") <subcommand> [args...]

Subcommands:
  extract-secrets <workflow-yaml>   Output GCP secret names referenced by
                                    update_secrets / set_secrets in the
                                    given workflow file.
EOF
}

cmd="${1:-}"
if [ -z "$cmd" ]; then
  usage
  exit 2
fi
shift

case "$cmd" in
  extract-secrets)
    if [ $# -ne 1 ]; then
      usage
      exit 2
    fi
    exec python3 "$script_dir/extract_secrets.py" "$1"
    ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    echo "error: unknown subcommand: $cmd" >&2
    usage
    exit 2
    ;;
esac
