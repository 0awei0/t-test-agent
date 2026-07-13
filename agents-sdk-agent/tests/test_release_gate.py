import unittest

from ai_test_officer.release_gate import ReleaseGateError, validate_run_record


class ReleaseGateTests(unittest.TestCase):
    def test_accepts_expected_deterministic_run(self) -> None:
        validate_run_record(
            {
                "verdict": "fail",
                "risk": "high",
                "commands": [{"command": "python -m unittest"}],
                "summary": "Unsafe release blocked.",
            },
            expected_verdict="fail",
            expected_risk="high",
        )

    def test_rejects_wrong_verdict(self) -> None:
        with self.assertRaisesRegex(ReleaseGateError, "unexpected verdict"):
            validate_run_record(
                {
                    "verdict": "pass",
                    "risk": "low",
                    "commands": [{"command": "python -m unittest"}],
                    "summary": "Passed.",
                },
                expected_verdict="fail",
                expected_risk="high",
            )

    def test_agent_gate_requires_complete_tool_evidence(self) -> None:
        with self.assertRaisesRegex(ReleaseGateError, "required Agent tool check failed"):
            validate_run_record(
                {
                    "verdict": "fail",
                    "risk": "high",
                    "commands": [{"command": "python -m unittest"}],
                    "summary": "Unsafe release blocked.",
                    "planner_mode": "agent-strict",
                    "required_tool_check": {"passed": False, "missing": ["read_test_log"]},
                    "agent_turns": [{"turn": 1}],
                    "agent_final_output": "Block release.",
                },
                expected_verdict="fail",
                expected_risk="high",
                require_agent_tools=True,
            )


if __name__ == "__main__":
    unittest.main()
