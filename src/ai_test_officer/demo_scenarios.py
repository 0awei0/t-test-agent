from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


SCENARIO_A_TASK = "场景A：分析刚提交的改动并跑针对性测试"
SCENARIO_A_FULLSTACK_TASK = (
    "场景A-fullstack：分析刚提交的后端改动，验证业务函数、HTTP API 和前端 checkout 流程"
)
SCENARIO_B_TASK = "场景B：读取需求文档，拆解测试场景，并检查功能点是否被实现"
SCENARIO_C_TASK = "场景C：执行核心功能巡检，发现异常后整理异常点、原因和通知摘要"


@dataclass(frozen=True)
class ScenarioDemo:
    key: str
    repo_path: Path
    task: str
    requirement_path: Path | None = None
    use_last_commit: bool = False


BASELINE_CHECKOUT = '''def discounted_total(subtotal_cents: int, discount_percent: int) -> int:
    """Return checkout total after applying a percentage discount."""

    if subtotal_cents < 0:
        raise ValueError("subtotal cannot be negative")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("discount_percent must be between 0 and 100")

    discount_cents = subtotal_cents * discount_percent // 100
    return subtotal_cents - discount_cents
'''


BUGGY_CHECKOUT = '''def discounted_total(subtotal_cents: int, discount_percent: int) -> int:
    """Return checkout total after applying a percentage discount."""

    if subtotal_cents < 0:
        raise ValueError("subtotal cannot be negative")
    if discount_percent < 0:
        raise ValueError("discount_percent must be non-negative")

    # Marketing now sends boosted discounts for VIP users. The cap was removed
    # accidentally, so callers can produce negative checkout totals.
    discount_cents = subtotal_cents * discount_percent // 100
    return subtotal_cents - discount_cents
'''


TEST_CHECKOUT = '''import unittest

from checkout import discounted_total


class CheckoutTests(unittest.TestCase):
    def test_applies_percentage_discount(self) -> None:
        self.assertEqual(discounted_total(10_000, 25), 7_500)

    def test_rejects_discount_above_100_percent(self) -> None:
        with self.assertRaises(ValueError):
            discounted_total(10_000, 120)


if __name__ == "__main__":
    unittest.main()
'''


FULLSTACK_TESTING_GUIDE = """# A-fullstack 演示说明

## 验证目标

这个合成仓库模拟开发刚提交 checkout 折扣逻辑后，AI 测试官需要同时验证：

- 业务函数 `discounted_total` 是否仍然拒绝超过 100 的折扣。
- HTTP API `/api/checkout` 是否把非法折扣返回为 400 错误。
- 前端 checkout 页面是否会向用户展示边界校验错误，而不是展示负数订单金额。

## 建议验证命令

```bash
uv run --with playwright python -m unittest discover -s tests -p 'test_*.py' -v
```

`tests/test_browser_checkout.py` 会驱动真实浏览器，
并把失败页面截图保存到 `reports/evidence/checkout-negative-total.png`。
"""


FULLSTACK_SERVER = '''from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from checkout import discounted_total


STATIC_DIR = Path(__file__).with_name("static")


class CheckoutHandler(BaseHTTPRequestHandler):
    server_version = "CheckoutDemo/1.0"

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._send_bytes((STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/api/checkout":
            self._send_json({"error": "not found"}, status=404)
            return

        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            subtotal = int(payload["subtotal_cents"])
            discount = int(payload["discount_percent"])
            total = discounted_total(subtotal, discount)
        except (KeyError, TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=400)
            return

        self._send_json({"total_cents": total})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(body, "application/json", status)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_test_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), CheckoutHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), CheckoutHandler)
    print("Serving checkout demo at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
'''


FULLSTACK_INDEX = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Checkout Demo</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem; color: #222; }
      main { max-width: 560px; }
      label { display: block; margin: 1rem 0 0.35rem; font-weight: 700; }
      input, button { font: inherit; padding: 0.55rem 0.7rem; }
      input { width: 100%; box-sizing: border-box; }
      button { margin-top: 1rem; border: 0; background: #0b6bcb; color: white; cursor: pointer; }
      #result { margin-top: 1.25rem; min-height: 1.5rem; font-weight: 700; }
      .error { color: #b42318; }
      .ok { color: #067647; }
    </style>
  </head>
  <body>
    <main>
      <h1>Checkout Demo</h1>
      <label for="subtotal">Subtotal cents</label>
      <input id="subtotal" type="number" value="10000" />
      <label for="discount">Discount percent</label>
      <input id="discount" type="number" value="25" />
      <button id="calculate" type="button">Calculate</button>
      <div id="result" role="status"></div>
    </main>
    <script>
      const result = document.querySelector("#result");
      document.querySelector("#calculate").addEventListener("click", async () => {
        result.className = "";
        result.textContent = "Checking...";
        const response = await fetch("/api/checkout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            subtotal_cents: Number(document.querySelector("#subtotal").value),
            discount_percent: Number(document.querySelector("#discount").value),
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          result.className = "error";
          result.textContent = payload.error;
          return;
        }
        result.className = "ok";
        result.textContent = `Payable total: ${payload.total_cents} cents`;
      });
    </script>
  </body>
</html>
'''


FULLSTACK_API_TEST = '''import json
import unittest
import urllib.error
import urllib.request

from server import start_test_server


class CheckoutApiTests(unittest.TestCase):
    def test_api_rejects_discount_above_100_percent(self) -> None:
        server, base_url = start_test_server()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        request = urllib.request.Request(
            f"{base_url}/api/checkout",
            data=json.dumps({"subtotal_cents": 10000, "discount_percent": 120}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)

        self.assertEqual(raised.exception.code, 400)
        body = raised.exception.read().decode("utf-8")
        self.assertIn("between 0 and 100", body)


if __name__ == "__main__":
    unittest.main()
'''


FULLSTACK_BROWSER_TEST = '''import unittest
from pathlib import Path

from server import start_test_server

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on optional e2e extra.
    sync_playwright = None


class CheckoutBrowserTests(unittest.TestCase):
    def test_page_rejects_discount_above_100_percent(self) -> None:
        if sync_playwright is None:
            self.skipTest("playwright is not installed; run uv run --with playwright python -m unittest")

        server, base_url = start_test_server()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        evidence_dir = Path("reports/evidence")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshot = evidence_dir / "checkout-negative-total.png"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 960, "height": 720})
                page.goto(base_url, wait_until="networkidle")
                page.fill("#subtotal", "10000")
                page.fill("#discount", "120")
                page.click("#calculate")
                page.wait_for_selector("#result")
                result = page.locator("#result").inner_text()
                page.screenshot(path=str(screenshot), full_page=True)
            finally:
                browser.close()

        self.assertIn("between 0 and 100", result)
        self.assertNotIn("-2000", result)


if __name__ == "__main__":
    unittest.main()
'''


SCENARIO_B_PRD = """# 结算折扣需求

## 背景

产品希望在结算页支持百分比折扣，但必须保证订单金额不会被折成负数。

## 功能要求

- `discounted_total(subtotal_cents, discount_percent)` 返回折扣后的金额，单位为分。
- `subtotal_cents` 不能为负数。
- `discount_percent` 必须在 0 到 100 之间，低于 0 或高于 100 都要拒绝。
- 当 `subtotal_cents=10000` 且 `discount_percent=25` 时，返回 `7500`。

## 验收重点

- 检查代码是否真的实现了 0-100 的折扣边界。
- 检查是否存在超过 100 折扣导致负数订单的风险。
"""


SCENARIO_C_PATROL = """# 核心链路巡检说明

## 巡检目标

每天定时检查 checkout health check，确保核心结算链路可用。

## 建议验证命令

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 判定规则

- 巡检通过：health check 返回 `ok`。
- 巡检失败：报告异常组件、失败命令、疑似原因和需要通知值班同学的摘要。
"""


SCENARIO_C_HEALTH = '''def checkout_health() -> dict[str, str]:
    """Return synthetic health status for the checkout patrol demo."""

    return {
        "checkout_api": "ok",
        "inventory_sync": "degraded",
        "payment_mock": "ok",
    }


def assert_core_path_ok() -> None:
    status = checkout_health()
    degraded = [name for name, value in status.items() if value != "ok"]
    if degraded:
        raise RuntimeError(f"core path degraded: {', '.join(degraded)}")
'''


SCENARIO_C_TEST = '''import unittest

from health_check import assert_core_path_ok, checkout_health


class PatrolTests(unittest.TestCase):
    def test_checkout_health_has_all_components(self) -> None:
        self.assertEqual(set(checkout_health()), {"checkout_api", "inventory_sync", "payment_mock"})

    def test_core_path_is_ok(self) -> None:
        assert_core_path_ok()


if __name__ == "__main__":
    unittest.main()
'''


def default_demo_root() -> Path:
    return Path(tempfile.gettempdir()) / "ai-test-officer-scenarios"


def ensure_scenario_demo(root: Path, scenario: str) -> ScenarioDemo:
    normalized = normalize_scenario_key(scenario)
    root = root.expanduser().resolve()
    if normalized == "A":
        repo = create_scenario_a_repo(root / "scenario-a")
        return ScenarioDemo("A", repo, SCENARIO_A_TASK, use_last_commit=True)
    if normalized == "A-fullstack":
        repo, guide = create_scenario_a_fullstack_repo(root / "scenario-a-fullstack")
        return ScenarioDemo(
            "A-fullstack",
            repo,
            SCENARIO_A_FULLSTACK_TASK,
            requirement_path=guide,
            use_last_commit=True,
        )
    if normalized == "B":
        repo, requirement = create_scenario_b_repo(root / "scenario-b")
        return ScenarioDemo("B", repo, SCENARIO_B_TASK, requirement_path=requirement)
    if normalized == "C":
        repo, requirement = create_scenario_c_repo(root / "scenario-c")
        return ScenarioDemo("C", repo, SCENARIO_C_TASK, requirement_path=requirement)
    raise ValueError(f"Unsupported scenario: {scenario}")


def ensure_all_scenario_demos(root: Path) -> dict[str, ScenarioDemo]:
    return {key: ensure_scenario_demo(root, key) for key in ("A", "A-fullstack", "B", "C")}


def normalize_scenario_key(text: str) -> str:
    upper = text.strip().upper()
    if upper in {"A", "SCENARIOA", "SCENARIO-A", "场景A"}:
        return "A"
    if upper in {"A-FULLSTACK", "AFULLSTACK", "SCENARIO-A-FULLSTACK", "FULLSTACK", "场景A-FULLSTACK"}:
        return "A-fullstack"
    if upper in {"B", "SCENARIOB", "SCENARIO-B", "场景B"}:
        return "B"
    if upper in {"C", "SCENARIOC", "SCENARIO-C", "场景C"}:
        return "C"
    raise ValueError(f"Unsupported scenario: {text}")


def create_scenario_a_repo(repo: Path) -> Path:
    if (repo / ".git").exists():
        return repo.resolve()

    repo.mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    _write(repo / "checkout.py", BASELINE_CHECKOUT)
    _write(repo / "tests" / "test_checkout.py", TEST_CHECKOUT)

    _git(repo, "init")
    _git(repo, "config", "user.email", "ai-test-officer@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline checkout discount behavior")

    _write(repo / "checkout.py", BUGGY_CHECKOUT)
    _git(repo, "add", "checkout.py")
    _git(repo, "commit", "-m", "feat: allow boosted checkout discounts")
    return repo.resolve()


def create_scenario_a_fullstack_repo(repo: Path) -> tuple[Path, Path]:
    if (repo / ".git").exists():
        return repo.resolve(), (repo / "fullstack-testing.md").resolve()

    repo.mkdir(parents=True, exist_ok=True)
    (repo / "static").mkdir(exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    _write(repo / "checkout.py", BASELINE_CHECKOUT)
    _write(repo / "server.py", FULLSTACK_SERVER)
    _write(repo / "static" / "index.html", FULLSTACK_INDEX)
    _write(repo / "tests" / "test_checkout.py", TEST_CHECKOUT)
    _write(repo / "tests" / "test_api.py", FULLSTACK_API_TEST)
    _write(repo / "tests" / "test_browser_checkout.py", FULLSTACK_BROWSER_TEST)
    _write(repo / "fullstack-testing.md", FULLSTACK_TESTING_GUIDE)

    _git(repo, "init")
    _git(repo, "config", "user.email", "ai-test-officer@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline fullstack checkout behavior")

    _write(repo / "checkout.py", BUGGY_CHECKOUT)
    _git(repo, "add", "checkout.py")
    _git(repo, "commit", "-m", "feat: allow boosted checkout discounts")
    return repo.resolve(), (repo / "fullstack-testing.md").resolve()


def create_scenario_b_repo(repo: Path) -> tuple[Path, Path]:
    if (repo / "prd.md").exists():
        return repo.resolve(), (repo / "prd.md").resolve()

    repo.mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    _write(repo / "checkout.py", BUGGY_CHECKOUT)
    _write(repo / "tests" / "test_checkout.py", TEST_CHECKOUT)
    _write(repo / "prd.md", SCENARIO_B_PRD)
    _init_git_once(repo, "scenario b requirement coverage demo")
    return repo.resolve(), (repo / "prd.md").resolve()


def create_scenario_c_repo(repo: Path) -> tuple[Path, Path]:
    if (repo / "patrol.md").exists():
        return repo.resolve(), (repo / "patrol.md").resolve()

    repo.mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    _write(repo / "health_check.py", SCENARIO_C_HEALTH)
    _write(repo / "tests" / "test_patrol.py", SCENARIO_C_TEST)
    _write(repo / "patrol.md", SCENARIO_C_PATROL)
    _init_git_once(repo, "scenario c patrol demo")
    return repo.resolve(), (repo / "patrol.md").resolve()


def _init_git_once(repo: Path, message: str) -> None:
    if (repo / ".git").exists():
        return
    _git(repo, "init")
    _git(repo, "config", "user.email", "ai-test-officer@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
