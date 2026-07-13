from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..execution.runner import RunConfig, run_test_officer
from ..models import RunRecord
from .fullstack import DemoRunConfig


def create_release_guard_demo(demo_root: Path, *, repaired: bool = False) -> Path:
    repo = demo_root.expanduser().resolve() / ("release-guard-pass" if repaired else "release-guard")
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    (repo / "static").mkdir()
    (repo / "tests").mkdir()
    _write_baseline(repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "demo@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline flash-sale order flow")
    _write_regression(repo)
    _git(repo, "add", "orders.py", "server.py", "static/index.html")
    _git(repo, "commit", "-m", "enable flash-sale stacked promotion")
    if repaired:
        _write_baseline(repo)
        _git(repo, "add", "orders.py", "server.py", "static/index.html")
        _git(repo, "commit", "-m", "restore release safeguards")
    return repo


def run_release_guard_demo(config: DemoRunConfig, *, repaired: bool = False) -> RunRecord:
    repo = config.demo_root.expanduser().resolve() / ("release-guard-pass" if repaired else "release-guard")
    if not repo.exists():
        repo = create_release_guard_demo(config.demo_root, repaired=repaired)
    task = (
        "发布守卫：分析大促订单变更，识别优惠、库存与支付幂等风险；"
        "自主选择单测、接口和浏览器验证，保留失败证据，并给出是否允许发布的明确建议。"
    )
    if repaired:
        task = (
            "修复验证：分析大促订单安全护栏恢复的变更，自主执行单测、接口和浏览器验证，"
            "再生成并运行 tests/test_agent_generated_release_guard.py，只补充验证 31% 优惠被拒绝、"
            "同一合法 request_id 重试不重复扣库存；任何命令失败后立即读取对应日志。"
            "确认优惠、库存与支付幂等保护均已恢复，并给出是否允许发布的明确建议。"
        )
    return run_test_officer(
        RunConfig(
            repo=repo,
            git_range=f"{_git(repo, 'rev-parse', 'HEAD~1')}..{_git(repo, 'rev-parse', 'HEAD')}",
            task=task,
            runs_root=config.runs_root,
            allow_temp_test_code=config.allow_temp_test_code,
            run_id=config.run_id,
            planner_mode=config.planner_mode,
            memory_mode=config.memory_mode,
            max_agent_turns=config.max_agent_turns,
        )
    )


def _write_baseline(repo: Path) -> None:
    (repo / "orders.py").write_text(
        '''from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    order_id: str
    payable_cents: int
    remaining_stock: int


class OrderService:
    def __init__(self, stock: int = 3):
        self.stock = stock
        self.orders = {}

    def checkout(self, quantity: int, coupon_percent: int, request_id: str) -> Order:
        if quantity < 1 or quantity > self.stock:
            raise ValueError("insufficient stock")
        if coupon_percent < 0 or coupon_percent > 30:
            raise ValueError("coupon exceeds release policy")
        if request_id in self.orders:
            return self.orders[request_id]
        self.stock -= quantity
        order = Order(request_id, quantity * 10000 * (100 - coupon_percent) // 100, self.stock)
        self.orders[request_id] = order
        return order

    def cancel(self, request_id: str) -> None:
        order = self.orders.pop(request_id)
        self.stock += (3 - order.remaining_stock)
''',
        encoding="utf-8",
    )
    (repo / "server.py").write_text(
        '''import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from orders import OrderService

SERVICE = OrderService()
ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)

    def do_POST(self):
        if urlparse(self.path).path != "/api/orders":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        try:
            order = SERVICE.checkout(int(body["quantity"]), int(body["coupon_percent"]), str(body["request_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, order.__dict__)

    def do_GET(self):
        if urlparse(self.path).path == "/api/stock":
            self._json(200, {"stock": SERVICE.stock})
            return
        if urlparse(self.path).path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def _json(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return


def make_server(port=0):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
''',
        encoding="utf-8",
    )
    (repo / "static" / "index.html").write_text(
        '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Flash Sale Console</title><style>
body{margin:0;background:#f2f6ff;color:#19233d;font:16px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{max-width:920px;margin:56px auto;padding:0 24px}.hero{background:linear-gradient(130deg,#152750,#315fd1);color:#fff;border-radius:24px;padding:34px;box-shadow:0 24px 48px #1d356033}.hero p{color:#ccdafd}.tag{display:inline-block;padding:5px 10px;border-radius:999px;background:#ffffff24;font-size:12px;font-weight:700}.grid{display:grid;grid-template-columns:1.3fr .7fr;gap:18px;margin-top:18px}.card{background:#fff;border:1px solid #dce5f8;border-radius:18px;padding:24px;box-shadow:0 10px 24px #172a5410}label{display:grid;gap:8px;font-weight:700;margin:16px 0}input{border:1px solid #b9c8e8;border-radius:10px;padding:12px;font-size:16px}button{border:0;border-radius:10px;background:#2555cf;color:#fff;padding:13px 18px;font-weight:800;cursor:pointer}#result{white-space:pre-wrap;min-height:86px;background:#f5f8ff;border-radius:10px;padding:14px;color:#384968}.metric{padding:13px 0;border-bottom:1px solid #e9eef9}.metric strong{display:block;font-size:24px;color:#2555cf}</style></head>
<body><main class="shell"><section class="hero"><span class="tag">Release candidate · Flash Sale</span><h1>大促订单发布控制台</h1><p>模拟优惠券、库存预占和支付重试的发布前验证。</p></section><section class="grid"><section class="card"><h2>创建预占订单</h2><label>优惠券折扣（发布策略上限 30%）<input id="coupon" value="45" inputmode="numeric"></label><button id="buy">提交订单预占</button><pre id="result">等待发布前校验…</pre></section><aside class="card"><h2>发布策略</h2><div class="metric"><strong>3</strong>库存可售</div><div class="metric"><strong>30%</strong>优惠上限</div><div class="metric"><strong>幂等</strong>支付重试保护</div></aside></section></main><script>document.querySelector("#buy").onclick=async()=>{result.textContent="订单校验中…";const response=await fetch("/api/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({quantity:1,coupon_percent:Number(coupon.value),request_id:"demo-order"})});result.textContent=await response.text()}</script></body></html>''',
        encoding="utf-8",
    )
    (repo / "tests" / "test_orders.py").write_text(
        '''import unittest
from orders import OrderService


class OrderPolicyTests(unittest.TestCase):
    def test_coupon_above_policy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "policy"):
            OrderService().checkout(1, 45, "promo-1")

    def test_retry_reuses_the_same_order_and_stock(self):
        service = OrderService()
        first = service.checkout(1, 20, "retry-1")
        second = service.checkout(1, 20, "retry-1")
        self.assertEqual(first, second)
        self.assertEqual(service.stock, 2)
''',
        encoding="utf-8",
    )
    (repo / "tests" / "test_api.py").write_text(
        '''import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import make_server


class OrderApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)

    def test_over_policy_coupon_returns_400(self):
        request = Request(f"{self.base}/api/orders", data=json.dumps({"quantity": 1, "coupon_percent": 45, "request_id": "api-1"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
''',
        encoding="utf-8",
    )
    (repo / "tests" / "test_browser.py").write_text(
        '''import threading
import unittest
from pathlib import Path

from server import make_server

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class CheckoutBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)

    def test_ui_rejects_an_unsafe_coupon(self):
        if sync_playwright is None:
            self.skipTest("Playwright unavailable")
        evidence = Path("reports/evidence")
        evidence.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1100, "height": 700})
            page.goto(self.base)
            page.locator("#buy").click()
            page.screenshot(path=str(evidence / "unsafe-coupon.png"), full_page=True)
            text = page.locator("#result").inner_text()
            browser.close()
        self.assertIn("coupon exceeds release policy", text)
''',
        encoding="utf-8",
    )


def _write_regression(repo: Path) -> None:
    orders = (repo / "orders.py").read_text(encoding="utf-8")
    orders = orders.replace("coupon_percent > 30", "coupon_percent > 60")
    orders = orders.replace(
        '''        if request_id in self.orders:
            return self.orders[request_id]
        self.stock -= quantity
''',
        '''        self.stock -= quantity
''',
    )
    (repo / "orders.py").write_text(orders, encoding="utf-8")
    server = (repo / "server.py").read_text(encoding="utf-8")
    (repo / "server.py").write_text(server.replace("SERVICE = OrderService()", "SERVICE = OrderService(stock=2)"), encoding="utf-8")
    page = (repo / "static" / "index.html").read_text(encoding="utf-8")
    (repo / "static" / "index.html").write_text(page.replace("Flash Sale Console", "Flash Sale Console · stacked promotion"), encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()
