import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.models import ChangedFile, RunRecord
from ai_test_officer.report_site import (
    export_fue_static_project,
    export_replay_catalog,
    publish_record,
    publish_report_path,
    write_local_replay_catalog,
)


class ReportSiteTests(unittest.TestCase):
    def test_publish_record_copies_html_json_markdown_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "run-1"
            evidence = run_dir / "repo" / "reports" / "evidence" / "checkout.png"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"png")
            (run_dir / "report.html").write_text('<img src="repo/reports/evidence/checkout.png">', encoding="utf-8")
            (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "manual-run",
                        "source_repo": str(root / "source"),
                        "workspace_repo": str(run_dir / "repo"),
                        "run_dir": str(run_dir),
                        "commands": [
                            {
                                "command": "python -m unittest -v",
                                "returncode": 1,
                                "stdout": "PRIVATE_STDOUT_" * 80,
                                "stderr": "AssertionError: checkout negative total\n" + "PRIVATE_STDERR_" * 80,
                                "log_path": str(run_dir / "logs" / "command-01.log"),
                                "failure_category": "test-failure",
                            }
                        ],
                        "memory_summary": {
                            "summary_path": str(run_dir / "memory" / "context_summary.md"),
                            "artifact_paths": [str(run_dir / "context" / "diff-index.json")],
                        },
                        "generated_files": [
                            {
                                "path": str(run_dir / "repo" / "tests" / "test_generated.py"),
                                "reason": "agent generated",
                            }
                        ],
                        "evidence_files": [str(evidence)],
                        "verdict": "fail",
                        "risk": "high",
                        "summary": "failed",
                    }
                ),
                encoding="utf-8",
            )
            record = RunRecord(
                run_id="run-1",
                task="demo",
                source_repo=root / "source",
                workspace_repo=run_dir / "repo",
                run_dir=run_dir,
                git_range="a..b",
                changed_files=[ChangedFile("M", "checkout.py")],
                diff_text="",
                allow_temp_test_code=True,
                evidence_files=[evidence],
            )

            published = publish_record(
                record,
                site_root=root / "site",
                base_url="https://internal.example/reports/",
            )

            self.assertTrue(published.index_path.exists())
            self.assertTrue((published.run_dir / "repo" / "reports" / "evidence" / "checkout.png").exists())
            self.assertEqual(record.detail_url, "https://internal.example/reports/run-1/index.html")
            updated = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["detail_url"], record.detail_url)
            self.assertNotIn("file://", published.index_path.read_text(encoding="utf-8"))

    def test_publish_report_path_uses_existing_report_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "manual-run"
            run_dir.mkdir(parents=True)
            (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (run_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")

            published = publish_report_path(
                run_dir / "report.md",
                site_root=root / "site",
                base_url="https://internal.example/reports",
            )

            self.assertTrue(published.index_path.exists())
            self.assertTrue(published.detail_url)
            assert published.detail_url is not None
            self.assertTrue(published.detail_url.endswith("/index.html"))

    def test_export_fue_static_project_writes_deployable_static_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "manual-run"
            evidence = run_dir / "repo" / "reports" / "evidence" / "checkout.png"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"png")
            (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (run_dir / "report.html").write_text(
                '<html><body><img src="repo/reports/evidence/checkout.png"></body></html>',
                encoding="utf-8",
            )
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "manual-run",
                        "source_repo": str(root / "source"),
                        "workspace_repo": str(run_dir / "repo"),
                        "run_dir": str(run_dir),
                        "commands": [
                            {
                                "command": "python -m unittest -v",
                                "returncode": 1,
                                "stdout": "PRIVATE_STDOUT_" * 80,
                                "stderr": "AssertionError: checkout negative total\n" + "PRIVATE_STDERR_" * 80,
                                "log_path": str(run_dir / "logs" / "command-01.log"),
                                "failure_category": "test-failure",
                            }
                        ],
                        "memory_summary": {
                            "summary_path": str(run_dir / "memory" / "context_summary.md"),
                            "artifact_paths": [str(run_dir / "context" / "diff-index.json")],
                        },
                        "generated_files": [
                            {
                                "path": str(run_dir / "repo" / "tests" / "test_generated.py"),
                                "reason": "agent generated",
                            }
                        ],
                        "evidence_files": [str(evidence)],
                        "verdict": "fail",
                        "risk": "high",
                        "summary": "failed",
                    }
                ),
                encoding="utf-8",
            )

            with patch("ai_test_officer.report_site.FRONTEND_DIST", root / "missing-frontend-dist"):
                exported = export_fue_static_project(
                    run_dir / "report.md",
                    output=root / "fue-export",
                    project_slug="ai-test-officer-report",
                )

            self.assertTrue((exported.public_dir / "index.html").exists())
            self.assertTrue((exported.public_dir / "report.md").exists())
            self.assertTrue((exported.public_dir / "public-run.json").exists())
            self.assertFalse((exported.public_dir / "run.json").exists())
            self.assertTrue((exported.public_dir / "repo" / "reports" / "evidence" / "checkout.png").exists())
            self.assertTrue((exported.public_dir / "dashboard" / "repo" / "reports" / "evidence" / "checkout.png").exists())
            public_json = (exported.public_dir / "public-run.json").read_text(encoding="utf-8")
            self.assertIn("AssertionError", public_json)
            self.assertIn("logs/command-01.log", public_json)
            self.assertNotIn(str(root), public_json)
            self.assertNotIn("PRIVATE_STDOUT_" * 20, public_json)
            self.assertNotIn("PRIVATE_STDERR_" * 20, public_json)
            config = json.loads(exported.config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["type"], "web")
            self.assertEqual(config["framework"]["name"], "Other")
            self.assertEqual(config["framework"]["outputDirectory"], "public")
            self.assertTrue(config["deployConfig"]["enableStatic"])
            self.assertEqual(config["deployConfig"]["staticDirectory"], "public")
            deploy_doc = exported.deploy_doc_path.read_text(encoding="utf-8")
            self.assertIn("静态Web应用", deploy_doc)
            self.assertIn("*.fue.woa.com", deploy_doc)
            self.assertNotIn("file://", (exported.public_dir / "index.html").read_text(encoding="utf-8"))

    def test_export_sanitizes_dashboard_events_and_omits_raw_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "event-run"
            run_dir.mkdir(parents=True)
            (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (run_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")
            (run_dir / "events.jsonl").write_text(
                "\n".join(
                    json.dumps(event)
                    for event in [
                        {
                            "seq": 1,
                            "type": "tool_call",
                            "data": {"output": f"OPENAI_API_KEY=top-secret {root}"},
                        },
                        {"seq": 2, "type": "done", "data": {}},
                        {
                            "seq": 3,
                            "type": "phase",
                            "data": {"phase": "reporting", "status": "done"},
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            logs = run_dir / "logs"
            logs.mkdir()
            (logs / "command-01.log").write_text("OPENAI_API_KEY=top-secret", encoding="utf-8")
            (run_dir / "run.json").write_text(
                json.dumps({"run_id": "event-run", "run_dir": str(run_dir), "source_repo": str(root)}),
                encoding="utf-8",
            )

            with patch("ai_test_officer.report_site.FRONTEND_DIST", root / "missing-frontend-dist"):
                exported = export_fue_static_project(run_dir / "report.md", output=root / "export")

            events = (exported.public_dir / "dashboard" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("top-secret", events)
            self.assertNotIn(str(root), events)
            exported_events = [json.loads(line) for line in events.splitlines()]
            self.assertEqual(exported_events[-1]["type"], "done")
            self.assertEqual([event["seq"] for event in exported_events], [1, 2, 3])
            self.assertFalse((exported.public_dir / "dashboard" / "logs").exists())

    def test_exports_multiple_sanitized_replays_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "task-45"
            evidence = run_dir / "evidence" / "shot.png"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"png")
            (run_dir / "report.html").write_text("<html>report</html>", encoding="utf-8")
            (run_dir / "events.jsonl").write_text(
                json.dumps({"seq": 1, "type": "done", "data": {}}) + "\n",
                encoding="utf-8",
            )
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "task-45",
                        "verdict": "fail",
                        "risk": "high",
                        "run_dir": str(run_dir),
                        "memory_summary": {"compression_ratio": 0.4},
                    }
                ),
                encoding="utf-8",
            )
            replay_runs = {"task-45": ("release-guard", run_dir)}

            local = write_local_replay_catalog(root / "runs", replay_runs, default_task_id="task-45")
            manifest = export_replay_catalog(replay_runs, root / "public", default_task_id="task-45")

            self.assertEqual(json.loads(local.read_text())["default_task_id"], "task-45")
            exported = json.loads(manifest.read_text())
            self.assertEqual(exported["items"][0]["verdict"], "fail")
            self.assertEqual(exported["items"][0]["compression_ratio"], 0.4)
            self.assertTrue((root / "public" / "replays" / "task-45" / "events.jsonl").exists())
            self.assertTrue((root / "public" / "replays" / "task-45" / "evidence" / "shot.png").exists())


if __name__ == "__main__":
    unittest.main()
