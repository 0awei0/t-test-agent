import tempfile
import unittest
from pathlib import Path

from ai_test_officer.execution.planner import plan_test_commands
from ai_test_officer.models import ChangedFile


class PlannerTests(unittest.TestCase):
    def test_selects_jest_and_playwright_for_javascript_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "packages" / "sdk").mkdir(parents=True)
            (repo / "packages" / "sdk" / "package.json").write_text(
                '{"scripts":{"test":"jest"}}', encoding="utf-8"
            )
            (repo / "apps" / "example").mkdir(parents=True)
            (repo / "apps" / "example" / "package.json").write_text(
                '{"scripts":{"test:e2e":"playwright test"}}',
                encoding="utf-8",
            )

            commands = plan_test_commands(
                [
                    ChangedFile("A", "packages/sdk/tests/network.test.ts"),
                    ChangedFile("A", "apps/example/tests/checkout.spec.ts"),
                ],
                repo,
            )

        self.assertIn("npm --prefix packages/sdk test", commands)
        self.assertIn("npm --prefix apps/example run test:e2e", commands)

    def test_selects_existing_e2e_script_when_default_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "apps" / "example").mkdir(parents=True)
            (repo / "apps" / "example" / "package.json").write_text(
                '{"scripts":{"test:e2e:real":"playwright test --config playwright.real.config.ts"}}',
                encoding="utf-8",
            )

            commands = plan_test_commands(
                [ChangedFile("M", "apps/example/tests/real-backend.spec.ts")],
                repo,
            )

        self.assertEqual(commands, ["npm --prefix apps/example run test:e2e:real"])


if __name__ == "__main__":
    unittest.main()
