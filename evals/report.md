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
| incident_triage | 3 | 3 | 0 | 100.0% |
| **Total** | **13** | **13** | **0** | **100.0%** |

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
[PASS] triage-001 status=PAUSED, severity_level=P1, stage=human_approval
[PASS] triage-002 status=COMPLETED, severity_level=P4, stage=resolution_report
[PASS] triage-003 status=PAUSED, severity_level=P2, stage=human_approval

Summary
Executed: 13
Passed:   13
Skipped:  0
Failed:   0
Pass rate: 100.0%
```

## Notes

- Triage eval now asserts `current_stage` in addition to `final_status` — all 3 pass.
- MCP integration test runs through FastAPI TestClient (ASGI in-process) — no real HTTP server needed.
