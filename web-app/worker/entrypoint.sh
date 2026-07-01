#!/usr/bin/env bash
#
# Container entrypoint for the QA Studio worker image.
#
# Two modes, selected by WORKER_MODE:
#   - batch  (default)  — invokes `qa-studio run` with flags derived from
#                         ECS env vars.  Matches the CLI-unified-runner
#                         entrypoint plan (R-WORKER-2 / R-WORKER-3 in
#                         .kiro/specs/cli-unified-runner/).
#   - wizard            — defers to the legacy wizard_worker.py until
#                         the wizard migration lands (R-WORKER-4).
#
# All environment translation lives here; the CLI itself never reads
# the raw ECS env vars.

set -euo pipefail

log() {
  printf '%s entrypoint: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 64
}

# Read an SSM parameter value using boto3.  We use the Python runtime
# we already ship rather than the `aws` CLI so the image doesn't need
# to bundle awscli v2.  Errors are surfaced verbatim on stderr instead
# of swallowed, so CloudWatch shows the real cause (missing param,
# missing IAM permission, network failure).
read_ssm_parameter() {
  local param_name="$1"
  python3 - "$param_name" <<'PY'
import sys
import boto3
from botocore.exceptions import BotoCoreError, ClientError

name = sys.argv[1]
try:
    client = boto3.client("ssm")
    response = client.get_parameter(Name=name)
except (BotoCoreError, ClientError) as exc:
    # Write the real cause to stderr so the entrypoint log keeps it.
    print(f"SSM get-parameter failed for {name}: {exc}", file=sys.stderr)
    sys.exit(1)
print(response["Parameter"]["Value"])
PY
}

WORKER_MODE="${WORKER_MODE:-batch}"

# ── Wizard branch — defer to the legacy worker script ───────────────
if [ "${WORKER_MODE}" = "wizard" ]; then
  log "WORKER_MODE=wizard — delegating to wizard_worker.py"
  cd /app
  exec python wizard_worker.py
fi

# ── Batch branch — invoke the unified CLI ───────────────────────────
log "WORKER_MODE=${WORKER_MODE} — invoking qa-studio run"

# Resolve the QA Studio API URL from SSM.  QA_STUDIO_API_URL_SSM is set
# by the CDK worker stack; the parameter itself is written by the api
# stack.  The CLI expects QA_STUDIO_API_URL.
if [ -z "${QA_STUDIO_API_URL:-}" ]; then
  if [ -n "${QA_STUDIO_API_URL_SSM:-}" ]; then
    log "Resolving API URL from SSM parameter ${QA_STUDIO_API_URL_SSM}"
    if ! QA_STUDIO_API_URL="$(read_ssm_parameter "${QA_STUDIO_API_URL_SSM}")"; then
      die "Failed to read SSM parameter ${QA_STUDIO_API_URL_SSM}"
    fi
  else
    die "QA_STUDIO_API_URL not set and QA_STUDIO_API_URL_SSM not provided"
  fi
fi
export QA_STUDIO_API_URL

# Resolve the Cognito token endpoint from SSM.  OAUTH_CLIENT_ID and
# OAUTH_CLIENT_SECRET come straight from ECS `secrets:` injection so
# we only need to add OAUTH_TOKEN_ENDPOINT here.  These three env vars
# are the contract of qa_studio_cli/auth/resolver.py.
if [ -z "${OAUTH_TOKEN_ENDPOINT:-}" ]; then
  if [ -n "${QA_STUDIO_TOKEN_ENDPOINT_SSM:-}" ]; then
    log "Resolving token endpoint from SSM parameter ${QA_STUDIO_TOKEN_ENDPOINT_SSM}"
    if ! OAUTH_TOKEN_ENDPOINT="$(read_ssm_parameter "${QA_STUDIO_TOKEN_ENDPOINT_SSM}")"; then
      die "Failed to read SSM parameter ${QA_STUDIO_TOKEN_ENDPOINT_SSM}"
    fi
  else
    die "OAUTH_TOKEN_ENDPOINT not set and QA_STUDIO_TOKEN_ENDPOINT_SSM not provided"
  fi
fi
export OAUTH_TOKEN_ENDPOINT

# Required inputs — fail fast with a clear message if the task def is
# misconfigured.
: "${USECASE_ID:?USECASE_ID env var is required for batch mode}"
: "${EXECUTION_ID:?EXECUTION_ID env var is required for batch mode}"
: "${OAUTH_CLIENT_ID:?OAUTH_CLIENT_ID must be injected by ECS secrets (from Secrets Manager)}"
: "${OAUTH_CLIENT_SECRET:?OAUTH_CLIENT_SECRET must be injected by ECS secrets (from Secrets Manager)}"

# ── Build the qa-studio run command ────────────────────────────────
cmd=(qa-studio run
  --usecase-id "${USECASE_ID}"
  --execution-id "${EXECUTION_ID}"
  --browser agentcore
  --format json
)

# AWS region — the runner forwards this to NovaAct Workflow.
if [ -n "${AWS_REGION:-}" ]; then
  cmd+=(--region "${AWS_REGION}")
fi

# Trajectory replay is controlled by the ENABLE_TRAJECTORY_REPLAY env
# var (read directly by the engine).  No CLI flag needed — setting
# the task definition env handles it.

# Verbose mode for easier debugging when running in CI.
if [ "${QA_STUDIO_VERBOSE:-false}" = "true" ]; then
  cmd+=(--verbose)
fi

log "Executing: ${cmd[*]}"
cd /app
exec "${cmd[@]}"
