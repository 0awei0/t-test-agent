from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..execution.runner import RunConfig, run_test_officer
from ..models import RunRecord
from .fullstack import DemoRunConfig


@dataclass(frozen=True)
class InvestigationCase:
    name: str
    module: str
    baseline: str
    regression: str
    contract_test: str
    task: str


CASES = {
    "promotion-chain": InvestigationCase(
        name="promotion-chain",
        module="pricing.py",
        baseline='''class PromotionEngine:
    def __init__(self, stock=2):
        self.stock = stock
        self.completed = {}

    def reserve(self, quantity, coupon_percent, request_id):
        if coupon_percent < 0 or coupon_percent > 30:
            raise ValueError("coupon exceeds policy")
        if request_id in self.completed:
            return self.completed[request_id]
        if quantity < 1 or quantity > self.stock:
            raise ValueError("insufficient stock")
        self.stock -= quantity
        order = {"id": request_id, "payable": quantity * 10000 * (100 - coupon_percent) // 100}
        self.completed[request_id] = order
        return order
''',
        regression='''class PromotionEngine:
    def __init__(self, stock=2):
        self.stock = stock
        self.completed = {}

    def reserve(self, quantity, coupon_percent, request_id):
        if coupon_percent < 0 or coupon_percent > 60:
            raise ValueError("coupon exceeds policy")
        if quantity < 1 or quantity > self.stock:
            raise ValueError("insufficient stock")
        self.stock -= quantity
        order = {"id": request_id, "payable": quantity * 10000 * (100 - coupon_percent) // 100}
        self.completed[request_id] = order
        return order
''',
        contract_test='''import unittest
from pricing import PromotionEngine


class PromotionContractTests(unittest.TestCase):
    def test_partner_coupon_cannot_exceed_release_policy(self):
        with self.assertRaisesRegex(ValueError, "policy"):
            PromotionEngine().reserve(1, 45, "campaign-1")
''',
        task=(
            "多轮调查：先读取 pricing.py 的 diff 和现有契约测试，运行该契约测试并读取失败日志。"
            "随后检查 request_id 的处理顺序，写入 tests/test_agent_generated_retry.py，证明同一支付重试不会重复扣减库存；"
            "运行生成的测试、读取其失败日志，再给出两个根因的发布建议。"
        ),
    ),
    "refund-guard": InvestigationCase(
        name="refund-guard",
        module="refunds.py",
        baseline='''class RefundService:
    def __init__(self):
        self.completed = {}

    def request(self, state, actor_role, paid_cents, refund_cents, request_id):
        if actor_role != "support":
            raise PermissionError("refund requires support role")
        if state != "paid":
            raise ValueError("refund requires paid order")
        if refund_cents <= 0 or refund_cents > paid_cents:
            raise ValueError("refund amount is invalid")
        if request_id in self.completed:
            return self.completed[request_id]
        result = {"id": request_id, "state": "refunded", "amount": refund_cents}
        self.completed[request_id] = result
        return result
''',
        regression='''class RefundService:
    def __init__(self):
        self.completed = {}

    def request(self, state, actor_role, paid_cents, refund_cents, request_id):
        if actor_role not in {"support", "customer"}:
            raise PermissionError("refund requires support role")
        if state not in {"paid", "shipped"}:
            raise ValueError("refund requires paid order")
        if refund_cents <= 0 or refund_cents > paid_cents:
            raise ValueError("refund amount is invalid")
        result = {"id": request_id, "state": "refunded", "amount": refund_cents}
        self.completed[request_id] = result
        return result
''',
        contract_test='''import unittest
from refunds import RefundService


class RefundContractTests(unittest.TestCase):
    def test_customer_cannot_refund_without_support_authorization(self):
        with self.assertRaises(PermissionError):
            RefundService().request("paid", "customer", 10000, 1000, "refund-1")
''',
        task=(
            "多轮调查：先读取 refunds.py 的 diff 和现有授权契约测试，运行测试并读取失败日志。"
            "随后检查订单状态机，写入 tests/test_agent_generated_refund_state.py，证明 shipped 状态不能退款；"
            "运行生成的测试、读取失败日志，并解释授权与状态机两个独立根因。"
        ),
    ),
}

INVESTIGATION_SCENARIOS = tuple(CASES)
PASS_SUFFIX = "-pass"


def create_investigation_demo(demo_root: Path, scenario: str) -> Path:
    case, repaired = _case_and_mode(scenario)
    repo = demo_root.expanduser().resolve() / f"{case.name}{PASS_SUFFIX if repaired else ''}"
    if repo.exists():
        shutil.rmtree(repo)
    (repo / "tests").mkdir(parents=True)
    (repo / case.module).write_text(case.baseline, encoding="utf-8")
    (repo / "tests" / "test_contract.py").write_text(case.contract_test, encoding="utf-8")
    (repo / "README.md").write_text(f"# {case.name}\n\nSynthetic multi-turn investigation demo.\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "demo@example.invalid")
    _git(repo, "config", "user.name", "AI Test Officer Demo")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline safety contract")
    (repo / case.module).write_text(case.regression, encoding="utf-8")
    _git(repo, "add", case.module)
    _git(repo, "commit", "-m", "relax release guard")
    if repaired:
        (repo / case.module).write_text(case.baseline, encoding="utf-8")
        _git(repo, "add", case.module)
        _git(repo, "commit", "-m", "restore release guard")
    return repo


def run_investigation_demo(config: DemoRunConfig, scenario: str) -> RunRecord:
    case, repaired = _case_and_mode(scenario)
    repo = config.demo_root.expanduser().resolve() / f"{case.name}{PASS_SUFFIX if repaired else ''}"
    if not repo.exists():
        repo = create_investigation_demo(config.demo_root, scenario)
    task = case.task
    if repaired:
        task = (
            f"修复验证：读取 {case.module} 的最新修复 diff 和现有契约测试，"
            "自主选择相关测试；再写入一个 tests/test_agent_generated_regression.py 临时边界测试并执行。"
            "优惠案例应验证 45% 被拒绝且同一合法 request_id 不重复扣库存；"
            "退款案例应验证 customer 与 shipped 状态都被拒绝。"
            "确认安全护栏已恢复，读取必要日志，并给出是否可发布的结论。"
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


def _case_and_mode(scenario: str) -> tuple[InvestigationCase, bool]:
    repaired = scenario.endswith(PASS_SUFFIX)
    base_scenario = scenario[: -len(PASS_SUFFIX)] if repaired else scenario
    try:
        return CASES[base_scenario], repaired
    except KeyError as exc:
        raise ValueError(f"unsupported investigation scenario: {scenario}") from exc


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()
