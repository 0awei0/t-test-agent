#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${AI_TEST_OFFICER_RUN_ID:-agent-loop-showcase}"
DEMO_ROOT="${AI_TEST_OFFICER_DEMO_ROOT:-runs/demos}"
RUNS_ROOT="${AI_TEST_OFFICER_RUNS_ROOT:-runs/showcase}"
FUE_DIR="${AI_TEST_OFFICER_FUE_DIR:-runs/fue-site/${RUN_ID}}"
PLANNER_MODE="${AI_TEST_OFFICER_PLANNER_MODE:-agent-strict}"
ENV_FILE="${AI_TEST_OFFICER_ENV_FILE:-.env}"

uv run ai-test-officer demo showcase \
  --scenario agent-loop \
  --demo-root "$DEMO_ROOT" \
  --runs-root "$RUNS_ROOT" \
  --planner-mode "$PLANNER_MODE" \
  --run-id "$RUN_ID" \
  --export-fue "$FUE_DIR" \
  --notify-dry-run \
  --env "$ENV_FILE"

uv run ai-test-officer demo doctor \
  --fue-public "$FUE_DIR/public" \
  --env "$ENV_FILE"

cat <<EOF

Showcase package is ready:
  $FUE_DIR

Deploy it with FUE:
  fue deploy --cwd "$FUE_DIR" --default

After FUE returns a https://*.fue.woa.com/... URL, send the WeCom summary:
  uv run ai-test-officer demo showcase \\
    --scenario agent-loop \\
    --demo-root "$DEMO_ROOT" \\
    --runs-root "$RUNS_ROOT" \\
    --planner-mode "$PLANNER_MODE" \\
    --run-id "$RUN_ID" \\
    --export-fue "$FUE_DIR" \\
    --detail-url <FUE_URL> \\
    --send \\
    --env "$ENV_FILE"
EOF
