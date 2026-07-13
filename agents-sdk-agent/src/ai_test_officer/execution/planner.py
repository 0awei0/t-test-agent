from __future__ import annotations

import json
from pathlib import Path

from ..models import ChangedFile, GeneratedFile
from ..tools import LocalTestTools


def generate_temp_tests(
    *,
    tools: LocalTestTools,
    changed_files: list[ChangedFile],
) -> list[GeneratedFile]:
    generated: list[GeneratedFile] = []
    for changed in changed_files:
        if not changed.path.endswith(".py"):
            continue
        source = tools.read_file(changed.path)
        if "def discounted_total" in source:
            generated.append(
                tools.write_temp_file(
                    "tests/test_generated_discount_boundary.py",
                    _discount_boundary_test(Path(changed.path)),
                    "Generated boundary regression test for discounted_total.",
                )
            )
    return generated


def plan_test_commands(changed_files: list[ChangedFile], repo_path: Path) -> list[str]:
    commands: list[str] = []
    go_dirs = sorted({str(Path(item.path).parent) for item in changed_files if item.path.endswith(".go")})
    for directory in go_dirs:
        commands.append(f"go test ./{directory} -count=1 -v")

    has_python = any(item.path.endswith(".py") for item in changed_files)
    if has_python and (repo_path / "tests").exists():
        commands.append("python -m unittest discover -s tests -p test_*.py -v")
    commands.extend(_javascript_test_commands(changed_files, repo_path))
    commands.extend(_rust_test_commands(changed_files, repo_path))
    return commands


def _javascript_test_commands(changed_files: list[ChangedFile], repo_path: Path) -> list[str]:
    commands: list[str] = []
    paths = [item.path for item in changed_files]
    for package_json in sorted(_changed_package_json_dirs(paths, repo_path)):
        command = _package_test_command(repo_path / package_json / "package.json", package_json)
        if command and command not in commands and not _has_package_command(commands, package_json):
            commands.append(command)
    return commands


def _package_test_command(package_json_path: Path, package_dir: Path) -> str | None:
    scripts = _package_scripts(package_json_path)
    if not scripts:
        return None
    script = _preferred_test_script(scripts)
    if script is None:
        return None
    prefix = package_dir.as_posix()
    if script == "test":
        return f"npm --prefix {prefix} test"
    return f"npm --prefix {prefix} run {script}"


def _package_scripts(package_json_path: Path) -> dict[str, str]:
    if not package_json_path.exists():
        return {}
    try:
        data = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items()}


def _preferred_test_script(scripts: dict[str, str]) -> str | None:
    for candidate in ("test:e2e", "test:e2e:real", "test:e2e:ui", "test"):
        if candidate in scripts:
            return candidate
    e2e_scripts = sorted(key for key in scripts if key.startswith("test:e2e"))
    if e2e_scripts:
        return e2e_scripts[0]
    test_scripts = sorted(key for key in scripts if key == "test" or key.startswith("test:"))
    return test_scripts[0] if test_scripts else None


def _changed_package_json_dirs(paths: list[str], repo_path: Path) -> set[Path]:
    dirs: set[Path] = set()
    for path in paths:
        if not path.endswith((".ts", ".tsx", ".js", ".jsx")):
            continue
        current = Path(path).parent
        while str(current) not in {"", "."}:
            if (repo_path / current / "package.json").exists():
                dirs.add(current)
                break
            current = current.parent
    return dirs


def _rust_test_commands(changed_files: list[ChangedFile], repo_path: Path) -> list[str]:
    commands: list[str] = []
    if not any(item.path.endswith(".rs") for item in changed_files):
        return commands
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        commands.append("cargo test --workspace")
    return commands


def _has_package_command(commands: list[str], package_dir: Path) -> bool:
    prefix = f"npm --prefix {package_dir.as_posix()} "
    return any(command.startswith(prefix) for command in commands)


def _discount_boundary_test(source_path: Path) -> str:
    module_name = source_path.with_suffix("").as_posix().replace("/", ".")
    return f'''import unittest

from {module_name} import discounted_total


class GeneratedDiscountBoundaryTest(unittest.TestCase):
    def test_discount_percent_above_100_is_rejected(self):
        with self.assertRaises(ValueError):
            discounted_total(10000, 120)


if __name__ == "__main__":
    unittest.main()
'''
