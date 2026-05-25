"""Non-blocking structured event emitter for LLM observability.

Writes structured JSON events to a JSONL log file for every LLM call,
capturing tokens, latency, and estimated cost. Never raises — all errors
are swallowed and printed to stderr.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import structlog

DEFAULT_LOG_PATH = "outputs/observability.jsonl"
DEFAULT_COST_PER_INPUT_TOKEN = 0.000003
DEFAULT_COST_PER_OUTPUT_TOKEN = 0.000015


class ObservabilityEmitter:
    """Emits structured JSONL events for LLM calls.

    Writes one JSON line per event to the configured log file.
    All methods are non-blocking: errors are logged to stderr and never
    propagate to the caller.
    """

    def __init__(self, log_path: str | None = None) -> None:
        self.log_path = log_path or os.getenv(
            "OBSERVABILITY_LOG_PATH", DEFAULT_LOG_PATH
        )
        self._logger = structlog.get_logger()
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(
                f"ObservabilityEmitter: could not create log directory: {exc}",
                file=sys.stderr,
            )

    def emit_llm_call(
        self,
        workflow_id: str,
        stage: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        """Emit a structured LLM call event.

        Non-blocking: wraps everything in try/except and writes errors to
        sys.stderr. Never raises.
        """
        try:
            cost_per_input = float(
                os.getenv("COST_PER_INPUT_TOKEN", str(DEFAULT_COST_PER_INPUT_TOKEN))
            )
            cost_per_output = float(
                os.getenv(
                    "COST_PER_OUTPUT_TOKEN", str(DEFAULT_COST_PER_OUTPUT_TOKEN)
                )
            )
            estimated_cost_usd = (
                input_tokens * cost_per_input + output_tokens * cost_per_output
            )

            event: Dict[str, Any] = {
                "event": "llm_call",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "workflow_id": workflow_id,
                "stage": stage,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "estimated_cost_usd": round(estimated_cost_usd, 6),
            }

            # Log via structlog for structured logging pipeline
            # Exclude "event" key to avoid collision with structlog's positional event arg
            structlog_event = {k: v for k, v in event.items() if k != "event"}
            self._logger.info("llm_call", **structlog_event)

            # Write directly to JSONL file
            line = json.dumps(event, default=str)
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

        except Exception as exc:
            print(f"ObservabilityEmitter error: {exc}", file=sys.stderr)


# Module-level singleton
try:
    default_emitter = ObservabilityEmitter()
except Exception as exc:
    print(
        f"ObservabilityEmitter: singleton init failed: {exc}",
        file=sys.stderr,
    )
    default_emitter = ObservabilityEmitter.__new__(ObservabilityEmitter)
    default_emitter.log_path = DEFAULT_LOG_PATH
    default_emitter._logger = structlog.get_logger()
