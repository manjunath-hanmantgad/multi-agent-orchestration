# Enterprise Agentic Workflow Platform — Architecture

## System Architecture

```mermaid
flowchart TD
    subgraph CL["CLIENT LAYER"]
        UI["Demo UI\n(Tailwind + FastAPI)"]
        RC["REST Clients\n/ Webhooks"]
        CLI["CLI / Dev Tools"]
    end

    subgraph GW["API GATEWAY"]
        FAPI["FastAPI\n/workflows  /approvals  /status  /audit\nAuth + Rate Limiting"]
    end

    subgraph ENG["WORKFLOW ENGINE CORE"]
        direction LR
        ORCH["LangGraph Orchestrator"]
        REG["Workflow Registry"]
        SM["State Manager\n(Checkpoints)"]
        HEM["Human Escalation\nManager"]
        AL["Audit Logger\n(Immutable)"]
        EB["Internal Event Bus"]
    end

    subgraph WM["WORKFLOW MODULES — pluggable"]
        direction LR
        CR["Compliance Review\nIntake > Rule Check > Risk Score\nPAUSE: Human Review\nDecision + Certificate"]
        PR["Procurement\nVendor Intake > Due Diligence\nPAUSE: Approval\nCRM Update"]
    end

    subgraph SVC["SUPPORTING SERVICES"]
        direction LR
        LLM["LLM Client\n(abstracted)"]
        DP["Document Parser\n(PDF/DOCX)"]
        RE["Rule Engine\n(configurable)"]
        NS["Notification\nService"]
        RG["Report Generator"]
    end

    subgraph DL["DATA LAYER"]
        direction LR
        WS[("SQLite\nWorkflow State")]
        AT[("Audit Trail\nAppend-only")]
        FS[("File Storage\ndocs + reports")]
        CRM[("Mock CRM")]
        AZ[("Azure Postgres\nprod-ready")]
    end

    UI --> FAPI
    RC --> FAPI
    CLI --> FAPI
    FAPI --> ORCH

    ORCH <--> REG
    ORCH <--> SM
    ORCH --> HEM
    ORCH --> AL
    ORCH <--> EB

    EB --> CR
    EB --> PR

    CR --> LLM
    CR --> DP
    CR --> RE
    CR --> RG
    PR --> LLM
    PR --> NS
    PR --> RG

    CR --> WS
    CR --> AT
    CR --> FS
    PR --> WS
    PR --> AT
    PR --> CRM
    SM --> WS
    AL --> AT
    WS -.->|"Azure-ready"| AZ

    style CR fill:#b2f2bb,stroke:#22c55e
    style PR fill:#b2f2bb,stroke:#22c55e
    style HEM fill:#ffd8a8,stroke:#f59e0b
    style AL fill:#c3fae8,stroke:#22c55e
    style EB fill:#fff3bf,stroke:#f59e0b
    style AZ fill:#ffc9c9,stroke:#ef4444
    style FAPI fill:#d0bfff,stroke:#8b5cf6
    style ORCH fill:#d0bfff,stroke:#8b5cf6
```

---

## Layer Descriptions

### Client Layer
| Component | Purpose |
|-----------|---------|
| Demo UI (Tailwind) | Browser-based dashboard: active workflows, human approval screen, audit trail, reports |
| REST Clients / Webhooks | External systems triggering workflows programmatically |
| CLI / Dev Tools | Developer trigger for testing and local runs |

### API Gateway (FastAPI)
Single entry point for all interactions. Routes:
- `POST /api/workflows/{type}/start` — trigger a new workflow run
- `GET  /api/workflows/{id}/status` — poll workflow state
- `POST /api/workflows/{id}/approve` — human submits approval decision
- `GET  /api/workflows/{id}/audit` — retrieve full audit trail
- `GET  /api/workflows` — list all active/completed workflows
- `GET  /api/health` — provider health check

### Workflow Engine Core
| Component | Responsibility |
|-----------|---------------|
| LangGraph Orchestrator | StateGraph-based multi-agent coordination; supports interrupt/resume |
| Workflow Registry | Discovers and loads workflow modules dynamically from `workflows/` |
| State Manager | Persists LangGraph checkpoints to SQLite; enables session recovery |
| Human Escalation Manager | Pauses workflow, records pending decision, resumes on human input |
| Audit Logger | Appends immutable event records for every state transition |
| Internal Event Bus | Routes events between engine components and workflow modules |

### Workflow Modules (pluggable)
Each workflow is a self-contained module implementing a standard interface:
```
class WorkflowModule:
    name: str
    description: str
    def build_graph() -> StateGraph
    def get_schema() -> WorkflowSchema
```

**Compliance Review** — highest-value enterprise workflow:
1. Intake — accept document/request, extract structured data
2. Rule Check — run configurable compliance rules
3. Risk Scoring — LLM-powered risk analysis with reasoning
4. **PAUSE** — workflow halts, human reviewer sees full context
5. Decision — approve / reject / request more info → certificate or rejection report

**Procurement** — demonstrates platform breadth:
1. Vendor Intake — structured vendor application
2. Due Diligence — automated background and risk check
3. **PAUSE** — approver reviews and decides
4. CRM Update — record outcome in mock CRM

### Supporting Services
| Service | Detail |
|---------|--------|
| LLM Client | Abstracted interface — swap Anthropic/OpenAI via env config |
| Document Parser | PDF and DOCX text extraction (pdfplumber + python-docx) |
| Rule Engine | JSON-configurable rules; returns pass/fail/flag per rule |
| Notification Service | Slack webhook stub; pluggable for prod notification systems |
| Report Generator | Produces structured PDF/JSON compliance certificates and rejection reports |

### Data Layer
| Store | Detail |
|-------|--------|
| SQLite — Workflow State | Active and historical workflow runs, current stage, metadata |
| Audit Trail | Immutable append-only event log (timestamp, actor, event, payload) |
| File Storage | Uploaded documents, generated reports (local path) |
| Mock CRM | SQLite table simulating a CRM for procurement outcomes |
| Azure Postgres | Drop-in replacement for SQLite in production; config-driven |

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Orchestration | LangGraph | Native checkpoint, interrupt/resume, conditional edges |
| Human-in-the-loop | Real API-driven pause | Demonstrates genuine persistence, not simulation |
| Workflow loading | Plugin registry | Shows platform thinking — new workflows = new module |
| LLM abstraction | Env-configured client | Demo works local (Anthropic) or cloud (Azure OpenAI) |
| Storage | SQLite → Azure Postgres | Zero-config local; single env var change for prod |
| Audit trail | Append-only events | Immutable by design — required for regulated industries |

---

## Compliance Review — State Machine Detail

```mermaid
stateDiagram-v2
    [*] --> Intake
    Intake --> RuleCheck : document extracted
    RuleCheck --> RiskScoring : rules evaluated
    RiskScoring --> HumanReview : risk score computed
    HumanReview --> [PAUSED] : workflow halts
    [PAUSED] --> Decision : human submits via UI
    Decision --> Approved : approve
    Decision --> Rejected : reject
    Decision --> RuleCheck : request more info
    Approved --> [*] : certificate generated
    Rejected --> [*] : rejection report generated
```

---

## Azure Production Path

All Azure services are documented but not required for local development:

| Local | Azure Production |
|-------|-----------------|
| SQLite | Azure Postgres Flexible Server |
| Local file storage | Azure Blob Storage |
| Anthropic API | Azure OpenAI |
| Slack webhook stub | Azure Service Bus + Logic Apps |
| uvicorn local | Azure Container Apps |
| .env file | Azure Key Vault + Managed Identity |
