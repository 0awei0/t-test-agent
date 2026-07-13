#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CHECK_BASE="${AI_TEST_OFFICER_CHECK_ROOT:-runs/competition-check}"
CHECK_ID="${AI_TEST_OFFICER_CHECK_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
CHECK_ROOT="$CHECK_BASE/$CHECK_ID"
PACKAGE_ROOT="$CHECK_ROOT/edgeone-site/competition-dashboard"
ENV_FILE="${AI_TEST_OFFICER_ENV_FILE:-.env}"
REPLAY_RUNS_ROOT="$CHECK_ROOT/mr-replays"
REPLAY_DEMO_ROOT="$CHECK_ROOT/mr-replay-demos"
REPLAY_BUILD_ARGS=()

if [[ "${AI_TEST_OFFICER_REUSE_REPLAYS:-0}" == "1" ]]; then
  REPLAY_RUNS_ROOT="${AI_TEST_OFFICER_REPLAY_RUNS_ROOT:-runs/mr-replays}"
  REPLAY_DEMO_ROOT="${AI_TEST_OFFICER_REPLAY_DEMO_ROOT:-runs/mr-replay-demos}"
  REPLAY_BUILD_ARGS+=(--reuse-existing)
  echo "INFO reusing locally ignored Agent replay runs from $REPLAY_RUNS_ROOT"
fi

run_step() {
  local label="$1"
  shift
  echo "RUN  $label"
  "$@"
  echo "PASS $label"
}

UV_VERSION="$(uv --version)"
if [[ "$UV_VERSION" != "uv 0.11.25"* ]]; then
  echo "FAIL uv version: expected 0.11.25, got $UV_VERSION" >&2
  exit 1
fi
echo "PASS uv version: $UV_VERSION"

run_step "Python lock" uv lock --check
run_step "Python environment" uv sync --locked --extra e2e --group dev
run_step "Python lint" uv run ruff check .
run_step "Python tests" uv run python -m unittest discover -s agents-sdk-agent/tests -p 'test_*.py' -v
run_step "Frontend install" npm --prefix frontend ci
run_step "Frontend typecheck" npm --prefix frontend run typecheck
run_step "Frontend build" npm --prefix frontend run build
run_step "Frontend audit" npm --prefix frontend audit --audit-level=moderate

run_step "Eight Agent replay package" \
  uv run python scripts/build_mr_replays.py \
    --runs-root "$REPLAY_RUNS_ROOT" \
    --demo-root "$REPLAY_DEMO_ROOT" \
    --dashboard-dir "$PACKAGE_ROOT" \
    --env "$ENV_FILE" \
    "${REPLAY_BUILD_ARGS[@]}"

run_step "Eight replay contracts and public safety" \
  uv run python -m ai_test_officer.replay_gate \
    --manifest "$PACKAGE_ROOT/replays/manifest.json" \
    --runs-root "$REPLAY_RUNS_ROOT" \
    --public-root "$PACKAGE_ROOT"

echo "READY competition package: $PACKAGE_ROOT"
