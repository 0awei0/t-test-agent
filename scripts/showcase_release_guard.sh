#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_TOKEN="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_ID="${AI_TEST_OFFICER_RUN_ID:-release-guard-showcase-${RUN_TOKEN}}"
DEMO_ROOT="${AI_TEST_OFFICER_DEMO_ROOT:-runs/demos}"
RUNS_ROOT="${AI_TEST_OFFICER_RUNS_ROOT:-runs/showcase}"
SITE_DIR="${AI_TEST_OFFICER_SITE_DIR:-runs/edgeone-site/${RUN_ID}}"
PLANNER_MODE="${AI_TEST_OFFICER_PLANNER_MODE:-agent-strict}"
ENV_FILE="${AI_TEST_OFFICER_ENV_FILE:-.env}"

uv run ai-test-officer demo showcase \
  --scenario release-guard \
  --demo-root "$DEMO_ROOT" \
  --runs-root "$RUNS_ROOT" \
  --planner-mode "$PLANNER_MODE" \
  --run-id "$RUN_ID" \
  --export-fue "$SITE_DIR" \
  --notify-dry-run \
  --env "$ENV_FILE"

uv run ai-test-officer demo doctor \
  --fue-public "$SITE_DIR/public" \
  --require-evidence \
  --env "$ENV_FILE"

uv run python -m ai_test_officer.release_gate \
  "$RUNS_ROOT/$RUN_ID/run.json" \
  --expect-verdict fail \
  --expect-risk high \
  --require-agent-tools

cat <<EOF

Release Guard showcase package is ready:
  $SITE_DIR

Deploy the public directory through EdgeOne Makers, then submit the resulting preview URL on the competition website.
EOF
