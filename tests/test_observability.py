"""Tests for core/observability.py — ObservabilityEmitter."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.observability import (
    DEFAULT_COST_PER_INPUT_TOKEN,
    DEFAULT_COST_PER_OUTPUT_TOKEN,
    ObservabilityEmitter,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def emitter(tmp_path: Path) -> ObservabilityEmitter:
    """Return an emitter that writes to a temporary JSONL file."""
    log_file = tmp_path / "test_observability.jsonl"
    return ObservabilityEmitter(log_path=str(log_file))


@pytest.fixture
def log_file(emitter: ObservabilityEmitter) -> Path:
    """Return the path to the emitter's log file."""
    return Path(emitter.log_path)


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestSuccessfulEmit:
    """Successful emit writes a valid JSONL entry."""

    def test_writes_valid_jsonl_with_all_fields(self, emitter, log_file):
        """After emit_llm_call, open the log file, parse last line as JSON,
        assert all 9 required fields are present and types are correct."""
        emitter.emit_llm_call(
            workflow_id="wf-test-1",
            stage="risk_scoring",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            latency_ms=1200,
        )
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        last_line = json.loads(lines[-1])

        assert last_line["event"] == "llm_call"
        assert isinstance(last_line["timestamp"], str)
        assert last_line["workflow_id"] == "wf-test-1"
        assert last_line["stage"] == "risk_scoring"
        assert last_line["model"] == "claude-sonnet-4-6"
        assert last_line["input_tokens"] == 500
        assert last_line["output_tokens"] == 200
        assert last_line["latency_ms"] == 1200
        assert isinstance(last_line["estimated_cost_usd"], float)

        # Verify all 9 required fields are present
        expected_fields = {
            "event",
            "timestamp",
            "workflow_id",
            "stage",
            "model",
            "input_tokens",
            "output_tokens",
            "latency_ms",
            "estimated_cost_usd",
        }
        assert expected_fields.issubset(set(last_line.keys()))


class TestNonBlocking:
    """Emitter never raises — all errors are swallowed and printed to stderr."""

    def test_file_write_failure_does_not_propagate(self, emitter, capsys):
        """Mock the file write to raise RuntimeError; assert the exception
        is NOT raised from emit_llm_call; assert error appears in stderr."""

        original_open = open

        def _failing_open(*args, **kwargs):
            raise RuntimeError("Simulated write failure")

        with patch("builtins.open", side_effect=_failing_open):
            # Should not raise despite the write failure
            emitter.emit_llm_call(
                workflow_id="wf-fail",
                stage="test",
                model="claude-sonnet-4-6",
                input_tokens=10,
                output_tokens=5,
                latency_ms=50,
            )

        stderr_output = capsys.readouterr().err
        assert "ObservabilityEmitter error" in stderr_output
        assert "Simulated write failure" in stderr_output


class TestDefaultEnvVars:
    """Missing env vars cause the emitter to fall back to default rates."""

    def test_missing_env_vars_use_defaults(self, emitter, log_file, monkeypatch):
        """Unset COST_PER_INPUT_TOKEN and COST_PER_OUTPUT_TOKEN; assert
        estimated_cost_usd is computed using default rates."""
        monkeypatch.delenv("COST_PER_INPUT_TOKEN", raising=False)
        monkeypatch.delenv("COST_PER_OUTPUT_TOKEN", raising=False)

        emitter.emit_llm_call(
            workflow_id="wf-defaults",
            stage="test",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=500,
        )

        lines = log_file.read_text().strip().split("\n")
        last_line = json.loads(lines[-1])
        expected_cost = (
            1000 * DEFAULT_COST_PER_INPUT_TOKEN
            + 500 * DEFAULT_COST_PER_OUTPUT_TOKEN
        )
        assert last_line["estimated_cost_usd"] == pytest.approx(expected_cost, rel=1e-9)


class TestCostCalculation:
    """Cost calculation matches the expected formula."""

    def test_cost_matches_expected_formula(self, emitter, log_file, monkeypatch):
        """Call with known input_tokens=1000, output_tokens=500, known rate
        env vars; assert estimated_cost_usd == 1000 * rate_in + 500 * rate_out."""
        monkeypatch.setenv("COST_PER_INPUT_TOKEN", "0.000005")
        monkeypatch.setenv("COST_PER_OUTPUT_TOKEN", "0.000020")

        emitter.emit_llm_call(
            workflow_id="wf-cost-test",
            stage="test",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=300,
        )

        lines = log_file.read_text().strip().split("\n")
        last_line = json.loads(lines[-1])
        expected_cost = 1000 * 0.000005 + 500 * 0.000020
        assert last_line["estimated_cost_usd"] == pytest.approx(expected_cost, rel=1e-9)
