#!/usr/bin/env python3
"""Eval runner for Multi-Agent Workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.escalation import _validate_decision
from core.services.rule_engine import RuleEngine
from workflows.compliance_review.schema import risk_payload


def run_rule_engine(case: dict) -> tuple[bool, str]:
    payload = case["input"]
    expected = case["expected"]

    engine = RuleEngine(workflows_root=str(Path(__file__).resolve().parents[1] / "workflows"))
    outcomes = engine.evaluate(payload["document_data"], payload["rules"])

    actual = {
        "passed": len(outcomes.get("passed", [])),
        "failed": len(outcomes.get("failed", [])),
        "flagged": len(outcomes.get("flagged", [])),
    }
    passed = actual == expected
    return passed, f"actual={actual}"


def run_escalation_trigger(case: dict) -> tuple[bool, str]:
    payload = case["input"]["risk_payload"]
    expected = case["expected"]

    try:
        _score, _reason = risk_payload(payload)
        should_trigger = True
        detail = f"validated score={_score}"
    except ValueError as exc:
        should_trigger = False
        detail = f"invalid payload: {exc}"

    passed = should_trigger == bool(expected["should_trigger"])
    return passed, detail


def run_state_transition(case: dict) -> tuple[bool, str]:
    decision = _validate_decision(case["input"]["decision"])
    next_status = "RUNNING" if decision == "REQUEST_MORE_INFO" else decision
    expected = case["expected"]["next_status"]
    passed = next_status == expected
    return passed, f"next_status={next_status}"


def main() -> int:
    dataset_path = Path(__file__).with_name("golden_dataset.json")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    runners = {
        "rule_engine": run_rule_engine,
        "escalation_trigger": run_escalation_trigger,
        "state_transition": run_state_transition,
    }

    executed = 0
    passed = 0
    skipped = 0
    failures: list[tuple[str, str]] = []

    for case in dataset["cases"]:
        case_id = case["id"]
        if case.get("requires_live_llm", False):
            skipped += 1
            print(f"[SKIP] {case_id} requires live LLM")
            continue

        runner = runners.get(case["category"])
        if runner is None:
            executed += 1
            failures.append((case_id, f"unsupported category: {case['category']}"))
            print(f"[FAIL] {case_id} unsupported category")
            continue

        ok, detail = runner(case)
        executed += 1
        if ok:
            passed += 1
            print(f"[PASS] {case_id} {detail}")
        else:
            failures.append((case_id, detail))
            print(f"[FAIL] {case_id} {detail}")

    print("\nSummary")
    print(f"Executed: {executed}")
    print(f"Passed:   {passed}")
    print(f"Skipped:  {skipped}")
    print(f"Failed:   {len(failures)}")
    if executed > 0:
        pass_rate = passed / executed * 100
        print(f"Pass rate: {pass_rate:.1f}%")
    else:
        print("Pass rate: N/A (no cases executed)")

    if failures:
        print("\nFailed cases:")
        for case_id, detail in failures:
            print(f"- {case_id}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
