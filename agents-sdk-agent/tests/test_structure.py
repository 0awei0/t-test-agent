import tempfile
import unittest
from pathlib import Path

from ai_test_officer.mcp import read_project_mcp_config, run_mcp_config_smoke
from ai_test_officer.skill import read_repo_skill


class StructureTests(unittest.TestCase):
    def test_reads_project_mcp_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("[mcp_servers.demo]\n", encoding="utf-8")

            config = read_project_mcp_config(root)

            self.assertIsNotNone(config)
            assert config is not None
            self.assertIn("mcp_servers.demo", config.text)

    def test_mcp_config_smoke_reports_missing_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("[mcp_servers.playwright]\n", encoding="utf-8")

            result = run_mcp_config_smoke(root)

            self.assertFalse(result.passed)
            self.assertIn("playwright", result.servers)
            self.assertIn("gongfeng", result.missing)

    def test_reads_repo_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / ".agents" / "skills" / "ai-test-officer"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# AI Test Officer\n", encoding="utf-8")

            skill = read_repo_skill(root)

            self.assertIsNotNone(skill)
            assert skill is not None
            self.assertIn("AI Test Officer", skill.text)


if __name__ == "__main__":
    unittest.main()
