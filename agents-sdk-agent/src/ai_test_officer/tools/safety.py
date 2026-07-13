from __future__ import annotations

import shlex
from pathlib import Path

from ..config import ALLOWED_FEATURE_ENV_NAME, ALLOWED_FEATURE_ENV_VALUES


class SafetyError(ValueError):
    """Raised when a requested test action violates local safety policy."""


DANGEROUS_TOKENS = {
    "commit",
    "push",
    "merge",
    "rebase",
    "reset",
    "checkout",
    "switch",
    "pull",
    "clean",
    "stash",
    "tag",
    "deploy",
    "kubectl",
    "docker",
    "curl",
    "wget",
    "dtools",
    "rm",
    "rmdir",
    "unlink",
}

SHELL_CONTROL_TOKENS = {
    "|",
    "||",
    "&",
    "&&",
    ";",
    "<",
    ">",
    ">>",
    "2>",
    "2>>",
    "2>&1",
}

FEATURE_ENV_MARKERS = (
    "custompath",
    "custom_path",
    "e2e_custom_path",
    "e2e_feature_env",
    "feature_env",
    "feature-env",
    "trpc-env",
)


def validate_test_command(command: str) -> list[str]:
    if "\n" in command or "\r" in command:
        raise SafetyError(f"multi-line shell commands are not allowed: {command}")
    tokens = shlex.split(command)
    if not tokens:
        raise SafetyError("empty command is not allowed")
    validate_feature_environment_usage(command)
    _reject_shell_control(tokens, command)
    lowered = [token.lower() for token in tokens]
    if "git" in lowered or any(token in DANGEROUS_TOKENS for token in lowered):
        raise SafetyError(f"dangerous command is not allowed: {command}")

    head = lowered[0]
    if head == "go" and len(lowered) >= 2 and lowered[1] == "test":
        return tokens
    if head in {"python", "python3"} and _is_allowed_python(tokens):
        return tokens
    if head in {"pytest"}:
        return tokens
    if head == "uv" and len(tokens) >= 3 and lowered[1] == "run":
        validate_test_command(" ".join(shlex.quote(token) for token in _strip_uv_run_options(tokens[2:])))
        return tokens
    if head == "npm" and len(lowered) >= 2 and lowered[1] == "test":
        return tokens
    if head == "npm" and len(lowered) >= 3 and lowered[1] == "--prefix" and any(
        token == "test" or token.startswith("test:") for token in lowered
    ):
        return tokens
    if head in {"pnpm", "yarn"} and len(lowered) >= 2 and lowered[1] in {"test", "exec"}:
        return tokens
    if head in {"pnpm", "yarn"} and "playwright" in lowered and "test" in lowered:
        return tokens
    if head == "npx" and "playwright" in lowered and "test" in lowered:
        return tokens
    if head == "cargo" and len(lowered) >= 2 and lowered[1] == "test":
        return tokens

    raise SafetyError(f"command is outside the test whitelist: {command}")


def _reject_shell_control(tokens: list[str], command: str) -> None:
    for token in tokens:
        if token in SHELL_CONTROL_TOKENS:
            raise SafetyError(f"shell control operators are not allowed in test commands: {command}")
        if any(marker in token for marker in ("|", ";", "`", "$(", "<", ">")):
            raise SafetyError(f"shell control operators are not allowed in test commands: {command}")


def _strip_uv_run_options(tokens: list[str]) -> list[str]:
    stripped = list(tokens)
    while stripped:
        head = stripped[0]
        if head in {"--with", "--with-editable", "--group", "--extra"} and len(stripped) >= 2:
            stripped = stripped[2:]
            continue
        if head in {"--locked", "--frozen", "--isolated"}:
            stripped = stripped[1:]
            continue
        break
    return stripped


def validate_feature_environment_usage(text: str) -> None:
    """Reject explicit feature-env routing outside the authorized test environment."""

    tokens = shlex.split(text)
    lowered = [token.lower() for token in tokens]
    for index, token in enumerate(lowered):
        value = _feature_env_value_from_token(tokens, lowered, index)
        if value is not None:
            _ensure_allowed_feature_env(value)


def _feature_env_value_from_token(tokens: list[str], lowered: list[str], index: int) -> str | None:
    token = tokens[index]
    lower = lowered[index]
    if lower in {"-env", "--env", "--envcode", "-e"} and index > 0 and lowered[index - 1] == "bpatch":
        return _next_token(tokens, index)
    if lower in {"-env", "--env", "--envcode"} and "dtools" in lowered:
        return _next_token(tokens, index)

    normalized = lower.replace("-", "_")
    if normalized in FEATURE_ENV_MARKERS:
        return _next_token(tokens, index)
    for marker in FEATURE_ENV_MARKERS:
        if normalized == marker.replace("-", "_") and index + 1 < len(tokens):
            return tokens[index + 1]

    for marker in FEATURE_ENV_MARKERS:
        marker_key = marker.replace("-", "_")
        if normalized.startswith(marker_key + "="):
            return token.split("=", 1)[1]
        if normalized.startswith(marker_key + ":"):
            return token.split(":", 1)[1]
    if lower.startswith("custompath:"):
        return token.split(":", 1)[1]
    return None


def _next_token(tokens: list[str], index: int) -> str | None:
    if index + 1 >= len(tokens):
        return None
    return tokens[index + 1]


def _ensure_allowed_feature_env(value: str | None) -> None:
    if value is None:
        return
    normalized = value.strip().strip("\"'")
    if normalized in ALLOWED_FEATURE_ENV_VALUES:
        return
    raise SafetyError(
        "feature environment is locked to "
        f"{ALLOWED_FEATURE_ENV_NAME}; refusing requested environment: {normalized}"
    )


def _is_allowed_python(tokens: list[str]) -> bool:
    if len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] in {"unittest", "pytest"}:
        for token in tokens[3:]:
            if "/" not in token:
                continue
            candidate = Path(token)
            if candidate.parts[:1] not in {("tests",), ("playwright",)}:
                return False
        return True
    if len(tokens) >= 2:
        candidate = Path(tokens[1])
        return candidate.parts[:1] in {("tests",), ("playwright",)} and candidate.suffix == ".py"
    return False


def validate_temp_write_path(repo_path: Path, relative_path: str, allow_temp_test_code: bool) -> Path:
    if not allow_temp_test_code:
        raise SafetyError("temporary test code is disabled; pass --allow-temp-test-code")

    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise SafetyError(f"unsafe relative path: {relative_path}")

    if not _is_allowed_temp_write_path(rel):
        raise SafetyError(f"temporary writes are limited to test and evidence paths: {relative_path}")

    target = (repo_path / rel).resolve()
    repo_resolved = repo_path.resolve()
    if repo_resolved not in target.parents and target != repo_resolved:
        raise SafetyError(f"path escapes workspace repo: {relative_path}")
    return target


def _is_allowed_temp_write_path(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    if parts[0] in {"tests", "playwright"}:
        return True
    if len(parts) >= 2 and parts[0] == "reports" and parts[1] == "evidence":
        return True
    if parts[0] == "evidence":
        return True
    name = path.name
    return len(parts) == 1 and ((name.startswith("test_") and path.suffix == ".py") or name.endswith("_test.go"))
