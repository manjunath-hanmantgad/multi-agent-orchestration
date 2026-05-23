# Architecture Extension — Multi-Agent Orchestration Platform

> This document covers ONLY the new layers added in the extension build. For the base platform architecture, see `docs/architecture.md`.

---

## What Is Being Added

```
┌─────────────────────────────────────────────────────────────┐
│           FRONTEND (NEW — TASK-08/09/10)                     │
│   Next.js 14 + shadcn/ui + Tailwind CSS                     │
│   Dashboard · Review · Audit Trail · Incident Triage        │
│   localhost:3000  →  calls FastAPI at localhost:8000         │
└─────────────────────────────────────────────────────────────┘
                           │ CORS
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXTENSION LAYERS (NEW)                    │
│                                                             │
│   MCP Server  ──►  Tool Registry  ──►  FastAPI Gateway      │
│   Observability Hooks  ──►  LLM Client  ──►  Telemetry Log  │
│   Eval Harness  ──►  Test Dataset  ──►  Quality Report       │
│   Incident Triage Workflow  ──►  WorkflowRegistry           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  BASE PLATFORM (UNCHANGED)                   │
│   LangGraph Engine · FastAPI Gateway · Audit Trail          │
│   Compliance Review · Procurement · Human Approval          │
│   Jinja2 app/ server — removed in TASK-10                   │
└─────────────────────────────────────────────────────────────┘
```

---

## System Architecture Delta

```mermaid
flowchart TD
    subgraph NEW["NEW — Extension Layers"]
        direction LR
        MCP["MCP Server\n(STDIO transport)\nmcp-server/server.py"]
        TR["Tool Registry\ncore/tool_registry.py\n4 tools registered"]
        OBS["Observability Layer\ncore/observability.py\nstructured JSONL log"]
        EVAL["Eval Harness\nevals/harness.py\nquality scorer + taxonomy"]
        IT["Incident Triage Module\nworkflows/incident_triage/\nP1–P4 severity + auto-resolve"]
    end

    subgraph MCP_TOOLS["MCP Tools (4)"]
        T1["start_workflow\n→ workflow_id, status"]
        T2["get_status\n→ status, stage, created_at"]
        T3["submit_decision\n→ APPROVE / REJECT"]
        T4["get_audit_trail\n→ ordered event timeline"]
    end

    subgraph EXISTING["EXISTING — Base Platform"]
        direction LR
        GW["FastAPI Gateway\nport 8000"]
        ENG["LangGraph Engine\nStateGraph + AsyncSqliteSaver"]
        LLMC["LLM Client\n(Anthropic / OpenAI)"]
        AT["Audit Trail\n(immutable append-only)"]
        WR["Workflow Registry\nauto-discovers modules"]
    end

    subgraph STORE["DATA / OUTPUT"]
        TLOG[("observability.jsonl\nappend-only telemetry")]
        EVAL_RPT["evals/report.md\nquality score + taxonomy"]
        WF_DB[("workflow_platform.db\nexisting SQLite")]
    end

    AGENT["LLM Agent\n(Claude Desktop / Claude Code)"] -->|"MCP protocol\n(STDIO)"| MCP
    MCP --> TR
    TR --> T1 & T2 & T3 & T4
    T1 & T2 & T3 & T4 -->|"HTTP calls\nhttpx"| GW

    GW --> ENG
    ENG --> LLMC
    LLMC -->|"structured event\non every call"| OBS
    OBS --> TLOG

    IT --> WR
    WR --> ENG

    EVAL -->|"runs mock scenarios"| GW
    EVAL --> EVAL_RPT

    ENG --> AT --> WF_DB

    style NEW fill:#dbeafe,stroke:#3b82f6
    style MCP fill:#ede9fe,stroke:#7c3aed
    style OBS fill:#fef3c7,stroke:#d97706
    style IT fill:#d1fae5,stroke:#059669
    style EVAL fill:#fce7f3,stroke:#db2777
    style EXISTING fill:#f9fafb,stroke:#6b7280
```

---

## MCP Server — Tool Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent as LLM Agent<br/>(Claude Desktop)
    participant MCP as MCP Server<br/>(STDIO)
    participant API as FastAPI Gateway<br/>:8000
    participant Engine as LangGraph Engine
    participant DB as SQLite Checkpoint

    Agent->>MCP: tool call: start_workflow({type, payload})
    MCP->>API: POST /api/workflows/start
    API->>Engine: build_graph(checkpointer)
    Engine->>Engine: run intake → rule_check → risk_score
    Engine->>DB: persist checkpoint (PAUSED)
    API-->>MCP: {workflow_id, status: PAUSED}
    MCP-->>Agent: "workflow_id: abc123\nstatus: PAUSED\nstage: human_review"

    Note over Agent,DB: Human reviews via dashboard UI

    Agent->>MCP: tool call: get_audit_trail({workflow_id})
    MCP->>API: GET /api/workflows/{id}/audit
    API-->>MCP: [{event, actor, timestamp}...]
    MCP-->>Agent: formatted event timeline (plain text)
```

---

## Incident Triage — State Machine

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Intake : incident description submitted
    Intake --> SeverityAssessment : text extracted + structured
    SeverityAssessment --> EscalationDecision : P1 / P2 / P3 / P4 scored
    EscalationDecision --> HumanApproval : P1 or P2\n(high severity)
    EscalationDecision --> ResolutionReport : P3 or P4\n(auto-resolve)
    HumanApproval --> Paused : workflow halts\ncheckpoint persisted
    Paused --> ResolutionReport : human submits decision
    ResolutionReport --> [*] : report generated + audit closed

    note right of EscalationDecision : Conditional edge —\nno separate graph
    note right of HumanApproval : Same interrupt pattern\nas compliance_review
```

---

## Observability — Data Flow

```mermaid
flowchart LR
    LLMC["LLM Client\ncore/llm_client.py"] -->|"try/finally\nnon-blocking"| OBS["Observability Emitter\ncore/observability.py"]
    OBS -->|"structlog JSON\nappend-only"| LOG["outputs/observability.jsonl"]
    LOG -->|"offline analysis\njq / pandas"| RPT["Cost + Usage Report\n(manual or scripted)"]

    OBS -->|"emit failure\n→ stderr only"| ERR["stderr\nno workflow impact"]

    style OBS fill:#fef3c7,stroke:#d97706
    style LOG fill:#d1fae5,stroke:#059669
    style ERR fill:#fee2e2,stroke:#dc2626
```

**JSONL event schema (one line per LLM call):**
```json
{
  "event": "llm_call",
  "timestamp": "2026-05-30T14:22:01Z",
  "workflow_id": "abc123",
  "stage": "risk_scoring",
  "model": "claude-sonnet-4-6",
  "input_tokens": 840,
  "output_tokens": 312,
  "latency_ms": 1420,
  "estimated_cost_usd": 0.00717
}
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP server calls FastAPI over HTTP | API client, not embedded module | Keeps MCP server independently deployable and testable; avoids coupling to LangGraph internals |
| STDIO transport (not Streamable HTTP) | STDIO for local dev | Zero config for Claude Desktop integration; Streamable HTTP is the Azure production step — deferred to keep scope tight |
| Observability is write-only from workflow perspective | Append-only JSONL | Adding read-back during workflow execution would couple telemetry to the hot path; offline analysis is sufficient |
| P3/P4 bypass implemented as conditional edge | Single graph, conditional routing | Adding a second graph or a separate function would break the WorkflowRegistry pattern; conditional edges are the LangGraph-native solution |
| Tool registry is a dict, not a database | In-memory catalog | Tools are registered at server startup and don't change at runtime; a database would add operational complexity for no benefit |
| Frontend: Next.js + shadcn/ui replacing Jinja2 | Next.js 14 App Router + shadcn/ui | Jinja2 + CDN Tailwind reads as a demo project to any enterprise evaluator; shadcn/ui components (built on Radix UI, used by Vercel/Linear/Loom) signal production-grade engineering; the 115k-star adoption means clients recognise the quality instantly |
| Frontend migration deferred to TASK-08/09/10 | Backend-first, frontend-last | MCP server and workflow module must be complete before UI is built; mixing frontend and backend tasks in the same sprint increases review complexity and risk of regression |
