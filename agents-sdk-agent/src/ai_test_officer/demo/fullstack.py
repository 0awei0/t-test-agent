from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_AGENT_MAX_TURNS
from ..execution.runner import RunConfig, run_test_officer
from ..models import RunRecord


@dataclass(frozen=True)
class DemoRunConfig:
    demo_root: Path
    planner_mode: str = "auto"
    allow_temp_test_code: bool = False
    runs_root: Path = Path("runs")
    run_id: str | None = None
    env: Path = Path(".env")
    memory_mode: str = "structured"
    max_agent_turns: int = DEFAULT_AGENT_MAX_TURNS


def create_fullstack_demo(demo_root: Path) -> Path:
    repo = demo_root.expanduser().resolve() / "fullstack"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    _write_baseline(repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "demo@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline checkout flow")
    _write_buggy_checkout(repo)
    _git(repo, "add", "checkout.py")
    _git(repo, "commit", "-m", "allow boosted checkout discounts")
    return repo


def create_agent_loop_demo(demo_root: Path) -> Path:
    repo = demo_root.expanduser().resolve() / "agent-loop"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "checkout.py").write_text(_baseline_checkout(), encoding="utf-8")
    (repo / "tests" / "test_checkout.py").write_text(_agent_loop_existing_test(), encoding="utf-8")
    (repo / "README.md").write_text(
        "# Agent Loop Demo\n\nMinimal repo where the agent must generate a missing boundary test.\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "demo@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline checkout function")
    _write_buggy_checkout(repo)
    _git(repo, "add", "checkout.py")
    _git(repo, "commit", "-m", "allow boosted discounts without upper bound")
    return repo


def run_fullstack_demo(config: DemoRunConfig) -> RunRecord:
    repo = config.demo_root.expanduser().resolve() / "fullstack"
    if not repo.exists():
        repo = create_fullstack_demo(config.demo_root)
    base = _git(repo, "rev-parse", "HEAD~1")
    head = _git(repo, "rev-parse", "HEAD")
    return run_test_officer(
        RunConfig(
            repo=repo,
            git_range=f"{base}..{head}",
            task=(
                "Fullstack demo: analyze the checkout discount change, run targeted "
                "unit/API/browser validation, preserve Playwright evidence when available, "
                "and explain whether the change is safe."
            ),
            runs_root=config.runs_root,
            allow_temp_test_code=config.allow_temp_test_code,
            run_id=config.run_id,
            planner_mode=config.planner_mode,
            memory_mode=config.memory_mode,
            max_agent_turns=config.max_agent_turns,
        )
    )


def run_agent_loop_demo(config: DemoRunConfig) -> RunRecord:
    repo = config.demo_root.expanduser().resolve() / "agent-loop"
    if not repo.exists():
        repo = create_agent_loop_demo(config.demo_root)
    base = _git(repo, "rev-parse", "HEAD~1")
    head = _git(repo, "rev-parse", "HEAD")
    return run_test_officer(
        RunConfig(
            repo=repo,
            git_range=f"{base}..{head}",
            task=(
                "Agent-loop demo: prove agentic testing by reading the checkout diff, "
                "writing a temporary boundary unittest for discount_percent > 100, "
                "running that generated test, reading the failure log, and explaining the regression."
            ),
            runs_root=config.runs_root,
            allow_temp_test_code=config.allow_temp_test_code,
            run_id=config.run_id,
            planner_mode=config.planner_mode,
            memory_mode=config.memory_mode,
            max_agent_turns=config.max_agent_turns,
            safety_probe=True,
        )
    )


def _write_baseline(repo: Path) -> None:
    (repo / "static").mkdir()
    (repo / "tests").mkdir()
    (repo / "checkout.py").write_text(_baseline_checkout(), encoding="utf-8")
    (repo / "server.py").write_text(_server(), encoding="utf-8")
    (repo / "static" / "index.html").write_text(_index_html(), encoding="utf-8")
    (repo / "tests" / "test_checkout.py").write_text(_unit_test(), encoding="utf-8")
    (repo / "tests" / "test_api_checkout.py").write_text(_api_test(), encoding="utf-8")
    (repo / "tests" / "test_browser_checkout.py").write_text(_browser_test(), encoding="utf-8")
    (repo / "README.md").write_text(
        "# Checkout Demo\n\nSynthetic fullstack repo for AI Test Officer validation.\n",
        encoding="utf-8",
    )


def _write_buggy_checkout(repo: Path) -> None:
    (repo / "checkout.py").write_text(_buggy_checkout(), encoding="utf-8")


def _baseline_checkout() -> str:
    return '''def discounted_total(total_cents, discount_percent):
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount must be between 0 and 100")
    return int(total_cents * (100 - discount_percent) / 100)
'''


def _buggy_checkout() -> str:
    return '''def discounted_total(total_cents, discount_percent):
    if discount_percent < 0:
        raise ValueError("discount must be non-negative")
    return int(total_cents * (100 - discount_percent) / 100)
'''


def _server() -> str:
    return r'''from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from checkout import discounted_total


ROOT = Path(__file__).resolve().parent


class CheckoutHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/checkout":
            return super().do_GET()
        params = parse_qs(parsed.query)
        try:
            total = int(params.get("total", ["10000"])[0])
            discount = int(params.get("discount", ["0"])[0])
            payable = discounted_total(total, discount)
        except Exception as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, {"total_cents": payable})

    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(port=0):
    return ThreadingHTTPServer(("127.0.0.1", port), CheckoutHandler)


if __name__ == "__main__":
    server = make_server(8000)
    print("serving on http://127.0.0.1:8000")
    server.serve_forever()
'''


def _index_html() -> str:
    return r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Checkout Demo</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 40px; color: #172033; }
    main { max-width: 560px; }
    label { display: block; margin: 12px 0 4px; }
    input { padding: 8px; width: 180px; }
    button { margin-top: 16px; padding: 9px 14px; }
    #result { margin-top: 18px; padding: 12px; border: 1px solid #d8dee8; border-radius: 8px; }
    .error { color: #9b1c16; }
    .ok { color: #126434; }
  </style>
</head>
<body>
<main>
  <h1>Checkout Demo</h1>
  <label>Total cents</label>
  <input id="total" value="10000">
  <label>Discount percent</label>
  <input id="discount" value="120">
  <br>
  <button id="checkout">Checkout</button>
  <div id="result">Waiting</div>
</main>
<script>
const result = document.querySelector("#result");
document.querySelector("#checkout").addEventListener("click", async () => {
  result.textContent = "Checking...";
  result.className = "";
  const total = document.querySelector("#total").value;
  const discount = document.querySelector("#discount").value;
  const response = await fetch(`/api/checkout?total=${total}&discount=${discount}`);
  const payload = await response.json();
  if (!response.ok) {
    result.textContent = `Invalid discount: ${payload.error}`;
    result.className = "error";
    return;
  }
  result.textContent = `Payable total: ${payload.total_cents} cents`;
  result.className = "ok";
});
</script>
</body>
</html>
'''


def _unit_test() -> str:
    return '''import unittest

from checkout import discounted_total


class CheckoutUnitTest(unittest.TestCase):
    def test_discount_above_100_is_rejected(self):
        with self.assertRaises(ValueError):
            discounted_total(10000, 120)

    def test_regular_discount(self):
        self.assertEqual(discounted_total(10000, 25), 7500)


if __name__ == "__main__":
    unittest.main()
'''


def _agent_loop_existing_test() -> str:
    return '''import unittest

from checkout import discounted_total


class CheckoutExistingTest(unittest.TestCase):
    def test_regular_discount(self):
        self.assertEqual(discounted_total(10000, 25), 7500)


if __name__ == "__main__":
    unittest.main()
'''


def _api_test() -> str:
    return r'''import json
import threading
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError

from server import make_server


class CheckoutApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)

    def test_discount_above_100_returns_400(self):
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"{self.base_url}/api/checkout?total=10000&discount=120", timeout=5)
        self.assertEqual(raised.exception.code, 400)

    def test_regular_discount_returns_total(self):
        with urlopen(f"{self.base_url}/api/checkout?total=10000&discount=25", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["total_cents"], 7500)


if __name__ == "__main__":
    unittest.main()
'''


def _browser_test() -> str:
    return r'''import threading
import unittest
from pathlib import Path

from server import make_server

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class CheckoutBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)

    def test_boosted_discount_shows_validation_error(self):
        if sync_playwright is None:
            self.skipTest(
                "Playwright is not installed. Run `uv sync --locked --extra e2e --group dev` "
                "and `uv run python -m playwright install chromium`."
            )
        evidence = Path("reports/evidence")
        evidence.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 900, "height": 640})
            page.goto(f"{self.base_url}/index.html")
            page.locator("#discount").fill("120")
            page.locator("#checkout").click()
            page.locator("#result").wait_for(state="visible")
            page.screenshot(path=str(evidence / "checkout-boosted-discount.png"), full_page=True)
            text = page.locator("#result").inner_text()
            browser.close()
        self.assertIn("Invalid discount", text)
        self.assertNotIn("-2000", text)


if __name__ == "__main__":
    unittest.main()
'''


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"git exited {proc.returncode}").strip()
        raise RuntimeError(detail)
    return proc.stdout.strip()
