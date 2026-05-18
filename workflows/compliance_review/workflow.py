"""LangGraph implementation for compliance review workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from core.registry import WorkflowModule
from core.state import StateManager
from workflows.compliance_review.agents import ComplianceReviewAgents, route_after_decision
from workflows.compliance_review.schema import (
    ComplianceReviewInput,
    ComplianceReviewOutput,
    ComplianceReviewState,
    build_initial_state,
)


class ComplianceReviewWorkflow(WorkflowModule):
    """Pluggable compliance review module with interrupt/resume support."""

    name = "compliance_review"
    description = "Compliance review workflow with human approval pause."

    def __init__(
        self,
        *,
        checkpointer: Any | None = None,
        agents: ComplianceReviewAgents | None = None,
        state_manager: StateManager | None = None,
    ) -> None:
        self._state_manager = state_manager
        self._agents = agents
        self._checkpointer = checkpointer
        self._compiled_graph: Any | None = None

    def get_input_schema(self) -> dict[str, Any]:
        """Return JSON schema for API input validation and discovery."""
        return ComplianceReviewInput.model_json_schema()

    def build_graph(self) -> Any:
        """Build and cache compiled graph using interrupt-before decision pattern."""
        if self._compiled_graph is None:
            checkpointer = _resolve_checkpointer(self)
            self._compiled_graph = _build_compiled_graph(_resolve_agents(self), checkpointer)
        return self._compiled_graph

    async def start(self, input_data: dict[str, Any]) -> ComplianceReviewOutput:
        """Start a new workflow run and execute until completion or human pause."""
        payload = ComplianceReviewInput.model_validate(input_data)
        initial_state = build_initial_state(payload)
        result_state = await self.build_graph().ainvoke(
            initial_state,
            config=_workflow_config(payload.workflow_id),
        )
        return _state_to_output(result_state)

    async def resume(self, workflow_id: str, decision: str, notes: str = "") -> ComplianceReviewOutput:
        """Inject human decision into paused run and resume graph execution."""
        graph = self.build_graph()
        config = _workflow_config(workflow_id)
        state_snapshot = await graph.aget_state(config)
        _require_checkpoint(state_snapshot.values, workflow_id)
        await graph.aupdate_state(
            config,
            {"human_decision": decision, "decision_notes": notes},
        )
        result_state = await graph.ainvoke(Command(resume=True), config=config)
        return _state_to_output(result_state)


def _build_compiled_graph(agents: ComplianceReviewAgents, checkpointer: Any) -> Any:
    """Create compiled StateGraph for compliance workflow."""
    builder = StateGraph(ComplianceReviewState)
    builder.add_node("intake_agent", agents.intake_agent)
    builder.add_node("rule_check_agent", agents.rule_check_agent)
    builder.add_node("risk_scoring_agent", agents.risk_scoring_agent)
    builder.add_node("human_review_node", agents.human_review_node)
    builder.add_node("decision_agent", agents.decision_agent)
    builder.add_node("certificate_agent", agents.certificate_agent)
    builder.add_node("rejection_agent", agents.rejection_agent)

    builder.add_edge(START, "intake_agent")
    builder.add_edge("intake_agent", "rule_check_agent")
    builder.add_edge("rule_check_agent", "risk_scoring_agent")
    builder.add_edge("risk_scoring_agent", "human_review_node")
    builder.add_edge("human_review_node", "decision_agent")
    builder.add_conditional_edges(
        "decision_agent",
        route_after_decision,
        {
            "certificate_agent": "certificate_agent",
            "rejection_agent": "rejection_agent",
            "rule_check_agent": "rule_check_agent",
        },
    )
    builder.add_edge("certificate_agent", END)
    builder.add_edge("rejection_agent", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["decision_agent"],
    )


def _build_default_agents(state_manager: StateManager | None) -> ComplianceReviewAgents:
    """Lazily build default agents only when graph execution is requested."""
    manager = state_manager or StateManager()
    return ComplianceReviewAgents(state_manager=manager)


def _resolve_agents(self: ComplianceReviewWorkflow) -> ComplianceReviewAgents:
    """Resolve configured agents, initializing defaults lazily."""
    if self._agents is None:
        self._agents = _build_default_agents(self._state_manager)
    return self._agents


def _resolve_checkpointer(self: ComplianceReviewWorkflow) -> Any:
    """Resolve checkpointer from explicit injection or API lifecycle injection."""
    if self._checkpointer is not None:
        return self._checkpointer
    try:
        from api import main as api_main
    except Exception:  # pragma: no cover - defensive import path
        api_main = None
    injected = getattr(api_main, "_checkpoint_saver", None) if api_main is not None else None
    if injected is None:
        raise ValueError("A checkpointer must be injected — InMemorySaver fallback is not permitted.")
    self._checkpointer = injected
    return injected


def _workflow_config(workflow_id: str) -> dict[str, dict[str, str]]:
    """Build LangGraph config using workflow_id as thread key."""
    return {"configurable": {"thread_id": workflow_id}}


def _require_checkpoint(values: Any, workflow_id: str) -> None:
    """Raise a clear error when resume is called before start."""
    if isinstance(values, dict) and values:
        return
    raise RuntimeError(f"No checkpoint found for workflow_id={workflow_id}")


def _state_to_output(state: dict[str, Any]) -> ComplianceReviewOutput:
    """Convert mutable graph state to structured workflow output."""
    return ComplianceReviewOutput(
        workflow_id=str(state.get("workflow_id", "")),
        status=str(state.get("status", "FAILED")),
        report_path=state.get("report_path"),
        risk_score=state.get("risk_score"),
        risk_reasoning=state.get("risk_reasoning"),
        human_decision=state.get("human_decision"),
        decision_notes=state.get("decision_notes"),
        error=state.get("error"),
    )
