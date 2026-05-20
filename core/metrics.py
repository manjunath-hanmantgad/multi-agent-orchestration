from prometheus_client import Counter, Histogram

_NS = "maw"

workflow_runs_total = Counter(
    f"{_NS}_workflow_runs_total",
    "Total workflow runs",
    ["workflow_type", "status"],
)
workflow_latency = Histogram(
    f"{_NS}_workflow_latency_seconds",
    "Workflow latency",
)
human_escalations_total = Counter(
    f"{_NS}_human_escalations_total",
    "Human review interrupts",
)
