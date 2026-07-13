import tempfile
import unittest
from pathlib import Path

from ai_test_officer.redaction import redact_secrets
from ai_test_officer.safety import (
    SafetyError,
    validate_feature_environment_usage,
    validate_temp_write_path,
    validate_test_command,
)


class SafetyTests(unittest.TestCase):
    def test_rejects_git_and_deploy_commands(self) -> None:
        for command in ["git push", "git commit -m x", "kubectl apply -f app.yaml", "curl http://x"]:
            with self.subTest(command=command):
                with self.assertRaises(SafetyError):
                    validate_test_command(command)

    def test_rejects_shell_control_operators(self) -> None:
        for command in [
            "go test ./service -v 2>&1 | head -50",
            "python -m unittest discover -s tests && echo ok",
            "npm --prefix packages/sdk test > out.log",
            "go test ./...\nrm -rf /tmp/x",
        ]:
            with self.subTest(command=command):
                with self.assertRaises(SafetyError):
                    validate_test_command(command)

    def test_allows_test_commands(self) -> None:
        self.assertEqual(validate_test_command("go test ./model -count=1"), ["go", "test", "./model", "-count=1"])
        self.assertEqual(
            validate_test_command("python -m unittest discover -s tests -p test_*.py -v")[:3],
            ["python", "-m", "unittest"],
        )
        self.assertEqual(validate_test_command("uv run python -m unittest -v")[:2], ["uv", "run"])
        self.assertEqual(
            validate_test_command("uv run --with playwright python -m unittest discover -s tests")[:4],
            ["uv", "run", "--with", "playwright"],
        )
        self.assertEqual(
            validate_test_command("npm --prefix packages/sdk test")[:3],
            ["npm", "--prefix", "packages/sdk"],
        )
        self.assertEqual(
            validate_test_command("npm --prefix apps/example run test:e2e")[:3],
            ["npm", "--prefix", "apps/example"],
        )
        self.assertEqual(validate_test_command("cargo test --workspace")[:2], ["cargo", "test"])

    def test_feature_env_is_locked_to_authorized_test_environment(self) -> None:
        validate_feature_environment_usage("customPath=authorized_test_env")
        validate_feature_environment_usage(
            "deployment-tool bpatch -env authorized_test_env_id -app example -server api"
        )
        validate_feature_environment_usage("E2E_CUSTOM_PATH=authorized_test_env npm test")
        for text in [
            "customPath=other_env",
            "customPath:another_env",
            "E2E_CUSTOM_PATH=unapproved_env npm test",
            "deployment-tool bpatch -env production -app example -server api",
        ]:
            with self.subTest(text=text):
                with self.assertRaises(SafetyError):
                    validate_feature_environment_usage(text)

    def test_temp_write_path_requires_flag_and_test_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(SafetyError):
                validate_temp_write_path(repo, "tests/test_generated.py", False)
            allowed = validate_temp_write_path(repo, "tests/test_generated.py", True)
            self.assertEqual(allowed, repo / "tests" / "test_generated.py")
            root_allowed = validate_temp_write_path(repo, "test_generated.py", True)
            self.assertEqual(root_allowed, repo / "test_generated.py")
            with self.assertRaises(SafetyError):
                validate_temp_write_path(repo, "app/service.py", True)
            with self.assertRaises(SafetyError):
                validate_temp_write_path(repo, "runs/nested/repo/test_generated.py", True)
            with self.assertRaises(SafetyError):
                validate_temp_write_path(repo, "../escape.py", True)

    def test_rejects_unittest_paths_outside_test_roots(self) -> None:
        with self.assertRaises(SafetyError):
            validate_test_command("python -m unittest runs/demo/repo/test_generated.py -v")
        self.assertEqual(
            validate_test_command("python -m unittest tests/test_generated.py -v")[:3],
            ["python", "-m", "unittest"],
        )

    def test_redacts_common_secrets(self) -> None:
        text = (
            "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz "
            "WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc-123"
        )
        redacted = redact_secrets(text)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("abc-123", redacted)
        self.assertIn("<redacted>", redacted)


if __name__ == "__main__":
    unittest.main()
