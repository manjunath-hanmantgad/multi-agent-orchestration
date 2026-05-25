# Eval Report — Multi-Agent Workflow

**Date:** 2026-05-24
**Dataset version:** 1.0
**Environment:** local

## Summary

| Category | Executed | Passed | Skipped | Pass Rate |
|---|---|---|---|---|
| rule_engine | 4 | 4 | 0 | 100.0% |
| escalation_trigger | 4 | 4 | 0 | 100.0% |
| state_transition | 2 | 2 | 0 | 100.0% |
| incident_triage | 0 | 0 | 3 | N/A (blocked) |
| **Total** | **10** | **10** | **3** | **100.0%** |

## Per-case output

```
[PASS] rule-001 actual={'passed': 1, 'failed': 0, 'flagged': 0}
[PASS] rule-002 actual={'passed': 1, 'failed': 0, 'flagged': 0}
[PASS] rule-003 actual={'passed': 0, 'failed': 1, 'flagged': 0}
[PASS] rule-004 actual={'passed': 0, 'failed': 0, 'flagged': 1}
[PASS] esc-001 validated score=80
[PASS] esc-002 validated score=10
[PASS] esc-003 invalid payload: risk scorer must return score 0-100 and non-empty reasoning
[PASS] esc-004 invalid payload: risk scorer must return score 0-100 and non-empty reasoning
[PASS] state-001 next_status=RUNNING
[PASS] state-002 next_status=APPROVED
[SKIP] triage-001 requires live LLM
[SKIP] triage-002 requires live LLM
[SKIP] triage-003 requires live LLM

Summary
Executed: 10
Passed:   10
Skipped:  3
Failed:   0
Pass rate: 100.0%
```

## Notes

- Incident triage cases (triage-001 to triage-003) are blocked until TASK-06 implements the incident_triage workflow module. They will be unblocked when `requires_live_llm` is set to `false` and a `run_incident_triage` runner is added.
- All 10 executed cases pass. No regressions from the base platform.
