import unittest
from pathlib import Path
from unittest.mock import patch

from ai_test_officer.integrations.gongfeng import (
    MrContext,
    MrFileChange,
    fetch_mr_context,
    mr_git_range,
    parse_mr_url,
    resolve_local_repo_for_mr,
)


class GongfengTests(unittest.TestCase):
    def test_parse_mr_url(self) -> None:
        parsed = parse_mr_url("https://git.woa.com/example/project/-/merge_requests/10")

        self.assertEqual(parsed.project_path, "example/project")
        self.assertEqual(parsed.iid, 10)
        self.assertEqual(parsed.project_api_id, "example%2Fproject")

    def test_fetch_mr_context_with_mock_api(self) -> None:
        responses = [
            {
                "id": 123,
                "title": "test mr",
                "state": "opened",
                "source_branch": "feature/a",
                "target_branch": "master",
            },
            {
                "files": [
                    {
                        "old_path": "/dev/null",
                        "new_path": "tests/example.spec.ts",
                        "diff": "+++ b/tests/example.spec.ts\n+test('x', () => {})\n",
                    }
                ]
            },
        ]

        with patch("ai_test_officer.integrations.gongfeng._get_json", side_effect=responses):
            context = fetch_mr_context("https://git.woa.com/example/project/-/merge_requests/10", token="token")

        self.assertEqual(context.project_path, "example/project")
        self.assertEqual(context.id, 123)
        self.assertEqual(context.files[0].status, "A")
        self.assertEqual(context.files[0].additions, 1)
        self.assertEqual(mr_git_range(context), "master..feature/a")

    def test_resolve_local_repo_uses_explicit_repo(self) -> None:
        repo = Path("/tmp/example")

        self.assertEqual(resolve_local_repo_for_mr("example/project", explicit_repo=repo), repo)


def _context() -> MrContext:
    return MrContext(
        url="https://git.woa.com/example/project/-/merge_requests/10",
        project_path="example/project",
        iid=10,
        id=123,
        title="title",
        state="opened",
        source_branch="feature",
        target_branch="master",
        source_sha=None,
        target_sha=None,
        files=[MrFileChange("M", "a.ts", "a.ts", "+x\n", 1, 0)],
    )


if __name__ == "__main__":
    unittest.main()
