"""LangGraph implementation for procurement workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from core.registry import WorkflowModule
from core.state import StateManager
from workflows.procurement.agents import ProcurementAgents, route_after_crm_update
from workflows.procurement.schema import (
    ProcurementInput,
    ProcurementOutput,
    ProcurementState,
    build_initial_state,
)


class ProcurementWorkflow(WorkflowModule):
    """Pluggable procurement module with human pause and CRM update."""

    name = "procurement"
    description = "Procurement due diligence workflow with human approval pause."

    def __init__(
        self,
        *,
        checkpointer: Any | None = None,
        agents: ProcurementAgents | None = None,
        state_manager: StateManager | None = None,
    ) -> None:
        self._state_manager = state_manager
        self._agents = agents
        self._checkpointer = checkpointer
        self._compiled_graph: Any | None = None

    def get_input_schema(self) -> dict[str, Any]:
        """Return JSON schema for API/request validation."""
        return ProcurementInput.model_json_schema()

    def build_graph(self) -> Any:
        """Build and cache compiled graph with interrupt-before human decision use."""
        if self._compiled_graph is None:
            checkpointer = _resolve_checkpointer(self)
            self._compiled_graph = _build_compiled_graph(_resolve_agents(self), checkpointer)
        return self._compiled_graph

    async def start(self, input_data: dict[str, Any]) -> ProcurementOutput:
        """Start run and execute until human pause or completion."""
        payload = ProcurementInput.model_validate(input_data)
        result = await self.build_graph().ainvoke(
            build_initial_state(payload),
            config=_workflow_config(payload.workflow_id),
        )
        return _state_to_output(result)

    async def resume(self, workflow_id: str, decision: str, notes: str = "") -> ProcurementOutput:
        """Inject human decision into paused run and continue execution."""
        graph = self.build_graph()
        config = _workflow_config(workflow_id)
        state_snapshot = await graph.aget_state(config)
        _require_checkpoint(state_snapshot.values, workflow_id)
        await graph.aupdate_state(config, {"human_decision": decision, "decision_notes": notes})
        result = await graph.ainvoke(Command(resume=True), config=config)
        return _state_to_output(result)


def _build_compiled_graph(agents: ProcurementAgents, checkpointer: Any) -> Any:
    """Create compiled StateGraph for procurement workflow."""
    builder = StateGraph(ProcurementState)
    builder.add_node("intake_agent", agents.intake_agent)
    builder.add_node("due_diligence_agent", agents.due_diligence_agent)
    builder.add_node("human_review_node", agents.human_review_node)
    builder.add_node("crm_update_agent", agents.crm_update_agent)

    builder.add_edge(START, "intake_agent")
    builder.add_edge("intake_agent", "due_diligence_agent")
    builder.add_edge("due_diligence_agent", "human_review_node")
    builder.add_edge("human_review_node", "crm_update_agent")
    builder.add_conditional_edges(
        "crm_update_agent",
        route_after_crm_update,
        {"due_diligence_agent": "due_diligence_agent", "end": END},
    )

    return builder.compile(checkpointer=checkpointer, interrupt_before=["crm_update_agent"])


def _build_default_agents(state_manager: StateManager | None) -> ProcurementAgents:
    """Lazily build default agents only when graph execution is requested."""
    manager = state_manager or StateManager()
    return ProcurementAgents(state_manager=manager)


def _resolve_agents(self: ProcurementWorkflow) -> ProcurementAgents:
    """Resolve configured agents, initializing defaults lazily."""
    if self._agents is None:
        self._agents = _build_default_agents(self._state_manager)
    return self._agents


def _resolve_checkpointer(self: ProcurementWorkflow) -> Any:
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
    """Build LangGraph config using workflow_id as thread id."""
    return {"configurable": {"thread_id": workflow_id}}


def _require_checkpoint(values: Any, workflow_id: str) -> None:
    """Raise a clear error when resume is called for missing checkpoints."""
    if isinstance(values, dict) and values:
        return
    raise RuntimeError(f"No checkpoint found for workflow_id={workflow_id}")


def _state_to_output(state: dict[str, Any]) -> ProcurementOutput:
    """Convert mutable graph state into structured output."""
    return ProcurementOutput(
        workflow_id=str(state.get("workflow_id", "")),
        status=str(state.get("status", "FAILED")),
        crm_record_id=state.get("crm_record_id"),
        due_diligence_result=state.get("due_diligence_result"),
        risk_summary=state.get("risk_summary"),
        human_decision=state.get("human_decision"),
        error=state.get("error"),
    )
