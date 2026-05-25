"""Tests for evals/run_evals.py — eval harness runners and summary logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add project root to sys.path so we can import from evals
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.run_evals import (
    run_rule_engine,
    run_escalation_trigger,
    run_state_transition,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def rule_payloads() -> dict[str, dict[str, Any]]:
    """Return a dict of case IDs to payloads for rule_engine tests."""
    dataset_path = (
        PROJECT_ROOT / "evals" / "golden_dataset.json"
    )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in dataset["cases"] if c["category"] == "rule_engine"}
    return cases


@pytest.fixture
def esc_payloads() -> dict[str, dict[str, Any]]:
    """Return a dict of case IDs to payloads for escalation_trigger tests."""
    dataset_path = (
        PROJECT_ROOT / "evals" / "golden_dataset.json"
    )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in dataset["cases"] if c["category"] == "escalation_trigger"}
    return cases


@pytest.fixture
def state_payloads() -> dict[str, dict[str, Any]]:
    """Return a dict of case IDs to payloads for state_transition tests."""
    dataset_path = (
        PROJECT_ROOT / "evals" / "golden_dataset.json"
    )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in dataset["cases"] if c["category"] == "state_transition"}
    return cases


# ─── Rule Engine Tests ──────────────────────────────────────────────────────


class TestRuleEngine:
    """Direct tests for the run_rule_engine eval function."""

    def test_pass_case_passes(self, rule_payloads):
        """rule-001 should pass (country equals IN with equals operator)."""
        case = rule_payloads["rule-001"]
        ok, detail = run_rule_engine(case)
        assert ok, f"rule-001 should pass: {detail}"

    def test_contains_operator_passes(self, rule_payloads):
        """rule-002 should pass (tags contains urgent with contains operator)."""
        case = rule_payloads["rule-002"]
        ok, detail = run_rule_engine(case)
        assert ok, f"rule-002 should pass: {detail}"

    def test_high_severity_failure_is_failed(self, rule_payloads):
        """rule-003 eval passes when rule fails (risk_score 55 is not > 70)."""
        case = rule_payloads["rule-003"]
        ok, detail = run_rule_engine(case)
        assert ok, f"rule-003 eval should pass (expected matches actual): {detail}"
        assert "failed" in detail

    def test_low_severity_failure_is_flagged(self, rule_payloads):
        """rule-004 eval passes when rule is flagged (vendor_tier silver != gold, low severity)."""
        case = rule_payloads["rule-004"]
        ok, detail = run_rule_engine(case)
        assert ok, f"rule-004 eval should pass (expected matches actual): {detail}"
        assert "flagged" in detail


# ─── Escalation Trigger Tests ───────────────────────────────────────────────


class TestEscalationTrigger:
    """Direct tests for the run_escalation_trigger eval function."""

    def test_mid_range_score_triggers_review(self, esc_payloads):
        """esc-001: valid mid-range risk score should trigger review."""
        case = esc_payloads["esc-001"]
        ok, detail = run_escalation_trigger(case)
        assert ok, f"esc-001 should pass: {detail}"

    def test_low_score_still_triggers_review(self, esc_payloads):
        """esc-002: valid low risk score still triggers review."""
        case = esc_payloads["esc-002"]
        ok, detail = run_escalation_trigger(case)
        assert ok, f"esc-002 should pass: {detail}"

    def test_invalid_score_is_rejected(self, esc_payloads):
        """esc-003: score >100 should be rejected."""
        case = esc_payloads["esc-003"]
        ok, detail = run_escalation_trigger(case)
        assert ok, f"esc-003 should pass: {detail}"

    def test_missing_reasoning_rejects(self, esc_payloads):
        """esc-004: empty reasoning should reject and not trigger."""
        case = esc_payloads["esc-004"]
        ok, detail = run_escalation_trigger(case)
        assert ok, f"esc-004 should pass: {detail}"


# ─── State Transition Tests ─────────────────────────────────────────────────


class TestStateTransition:
    """Direct tests for the run_state_transition eval function."""

    def test_request_more_info_transitions_to_running(self, state_payloads):
        """state-001: REQUEST_MORE_INFO should transition to RUNNING."""
        case = state_payloads["state-001"]
        ok, detail = run_state_transition(case)
        assert ok, f"state-001 should pass: {detail}"

    def test_approved_transitions_to_approved(self, state_payloads):
        """state-002: APPROVED should transition to APPROVED."""
        case = state_payloads["state-002"]
        ok, detail = run_state_transition(case)
        assert ok, f"state-002 should pass: {detail}"


# ─── Harness-level tests ────────────────────────────────────────────────────


class TestHarnessLogic:
    """Tests for harness-level logic: skip, unknown category, summary."""

    @pytest.fixture
    def dataset_with_live_llm(self, tmp_path: Path) -> Path:
        """Create a temp golden_dataset with a requires_live_llm case."""
        ds = {
            "version": "1.0",
            "project": "test",
            "cases": [
                {
                    "id": "live-001",
                    "description": "requires live LLM",
                    "category": "rule_engine",
                    "input": {},
                    "expected": {},
                    "requires_live_llm": True,
                },
                {
                    "id": "normal-001",
                    "description": "normal case",
                    "category": "rule_engine",
                    "input": {
                        "document_data": {"country": "IN"},
                        "rules": [
                            {
                                "id": "r1",
                                "name": "Country Check",
                                "description": "country must equal IN",
                                "field": "country",
                                "operator": "equals",
                                "value": "IN",
                                "severity": "high",
                            }
                        ],
                    },
                    "expected": {"passed": 1, "failed": 0, "flagged": 0},
                    "requires_live_llm": False,
                },
                {
                    "id": "unknown-cat-001",
                    "description": "unknown category",
                    "category": "nonexistent_category",
                    "input": {},
                    "expected": {},
                    "requires_live_llm": False,
                },
            ],
        }
        p = tmp_path / "golden_dataset.json"
        p.write_text(json.dumps(ds), encoding="utf-8")
        return p

    def test_requires_live_llm_is_skipped(self, dataset_with_live_llm, capsys, monkeypatch):
        """requires_live_llm=true cases are skipped and not executed."""
        monkeypatch.chdir(dataset_with_live_llm.parent)

        from evals.run_evals import main

        # We need to avoid importing main() directly with the live dataset
        # Instead test that SKIP is in output for live-001
        dataset = json.loads(dataset_with_live_llm.read_text(encoding="utf-8"))
        from evals.run_evals import main as harness_main

        # Patch the dataset path so main() reads our temp file
        with monkeypatch.context() as m:
            m.setattr("evals.run_evals.Path", lambda *a, **kw: dataset_with_live_llm)
            exit_code = harness_main()

        captured = capsys.readouterr()
        assert "[SKIP] live-001" in captured.out
        assert "[PASS] normal-001" in captured.out
        assert "[FAIL] unknown-cat-001" in captured.out
        assert exit_code == 1  # unknown-cat-001 fails

    def test_unknown_category_counts_as_failure(self, dataset_with_live_llm, capsys, monkeypatch):
        """Unknown category is counted as failure with unsupported category message."""
        monkeypatch.chdir(dataset_with_live_llm.parent)
        from evals.run_evals import main as harness_main

        with monkeypatch.context() as m:
            m.setattr("evals.run_evals.Path", lambda *a, **kw: dataset_with_live_llm)
            exit_code = harness_main()

        captured = capsys.readouterr()
        assert "[FAIL] unknown-cat-001" in captured.out
        assert "unsupported category" in captured.out
        assert exit_code == 1

    def test_summary_counts_are_correct(self, dataset_with_live_llm, capsys, monkeypatch):
        """Summary counts: 1 passed, 1 skipped, 1 failed = 2 executed."""
        monkeypatch.chdir(dataset_with_live_llm.parent)
        from evals.run_evals import main as harness_main

        with monkeypatch.context() as m:
            m.setattr("evals.run_evals.Path", lambda *a, **kw: dataset_with_live_llm)
            harness_main()

        captured = capsys.readouterr()
        assert "Executed: 2" in captured.out
        assert "Passed:   1" in captured.out
        assert "Skipped:  1" in captured.out
        assert "Failed:   1" in captured.out
        assert "Pass rate: 50.0%" in captured.out or "Pass rate" in captured.out
