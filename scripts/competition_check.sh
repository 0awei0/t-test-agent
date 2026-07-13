#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CHECK_BASE="${AI_TEST_OFFICER_CHECK_ROOT:-runs/competition-check}"
CHECK_ID="${AI_TEST_OFFICER_CHECK_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
CHECK_ROOT="$CHECK_BASE/$CHECK_ID"
DEMO_ROOT="$CHECK_ROOT/demos"
RUNS_ROOT="$CHECK_ROOT/runs"
PACKAGE_ROOT="$CHECK_ROOT/edgeone-site/release-guard"
ENV_FILE="${AI_TEST_OFFICER_ENV_FILE:-.env}"

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

run_step "Unsafe release scenario" \
  uv run ai-test-officer demo run \
    --scenario release-guard \
    --demo-root "$DEMO_ROOT" \
    --runs-root "$RUNS_ROOT" \
    --run-id release-guard \
    --planner-mode deterministic \
    --allow-temp-test-code \
    --env "$ENV_FILE"
run_step "Unsafe release contract" \
  uv run python -m ai_test_officer.release_gate \
    "$RUNS_ROOT/release-guard/run.json" \
    --expect-verdict fail \
    --expect-risk high

run_step "Repaired release scenario" \
  uv run ai-test-officer demo run \
    --scenario release-guard-pass \
    --demo-root "$DEMO_ROOT" \
    --runs-root "$RUNS_ROOT" \
    --run-id release-guard-pass \
    --planner-mode deterministic \
    --allow-temp-test-code \
    --env "$ENV_FILE"
run_step "Repaired release contract" \
  uv run python -m ai_test_officer.release_gate \
    "$RUNS_ROOT/release-guard-pass/run.json" \
    --expect-verdict pass \
    --expect-risk low

run_step "Public package export" \
  uv run ai-test-officer report export-fue \
    --report "$RUNS_ROOT/release-guard/report.md" \
    --output "$PACKAGE_ROOT" \
    --project-slug ai-test-officer-release-guard
run_step "Public package safety" \
  uv run ai-test-officer demo doctor \
    --fue-public "$PACKAGE_ROOT/public" \
    --require-evidence \
    --env "$ENV_FILE"

if [[ "${AI_TEST_OFFICER_REQUIRE_AGENT:-0}" == "1" ]]; then
  run_step "Agent tool loop" \
    uv run ai-test-officer demo run \
      --scenario agent-loop \
      --demo-root "$DEMO_ROOT" \
      --runs-root "$RUNS_ROOT" \
      --run-id agent-loop \
      --planner-mode agent-strict \
      --allow-temp-test-code \
      --env "$ENV_FILE"
  run_step "Agent tool contract" \
    uv run python -m ai_test_officer.release_gate \
      "$RUNS_ROOT/agent-loop/run.json" \
      --expect-verdict fail \
      --expect-risk high \
      --require-agent-tools
else
  echo "SKIP Agent tool loop; set AI_TEST_OFFICER_REQUIRE_AGENT=1 for the model-backed gate"
fi

echo "READY competition package: $PACKAGE_ROOT/public"
