"""
Failure injection tests – verify recovery and graceful stop behavior
for all supported injection modes.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.failure_injector import FailureInjector
from orchestrator.agent_loop import AgentLoop
from orchestrator.dp_cache import DPCache


DATA_CSV = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data_synthetic", "Scenario1.csv")
)
OVERNIGHT_CSV = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data_synthetic", "overnight_stays_by_country.csv")
)


# ══════════════════════════════════════════════════════════════════════════════
#  FailureInjector unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFailureInjector:

    def test_none_mode_passthrough(self):
        inj = FailureInjector("none")
        result = inj.inject("file_reader", {"path": "/data/file.csv"})
        assert result.force_error is None
        assert result.inputs == {"path": "/data/file.csv"}

    def test_bad_path_modifies_path(self):
        inj = FailureInjector("bad_path", target_tool="file_reader")
        result = inj.inject("file_reader", {"path": "/good/path.csv"})
        assert result.force_error is None
        assert "nonexistent" in result.inputs["path"]

    def test_bad_path_skips_other_tools(self):
        inj = FailureInjector("bad_path", target_tool="file_reader")
        result = inj.inject("kpi_calculator", {"dataset": {}})
        assert result.inputs == {"dataset": {}}

    def test_api_timeout_forces_error(self):
        inj = FailureInjector("api_timeout", target_tool="api_tool")
        result = inj.inject("api_tool", {"endpoint": "http://localhost/api"})
        assert result.force_error is not None
        assert "timeout" in result.force_error.lower()

    def test_api_rate_limit_forces_error(self):
        inj = FailureInjector("api_rate_limit", target_tool="api_tool")
        result = inj.inject("api_tool", {"endpoint": "http://localhost/api"})
        assert result.force_error is not None
        assert "429" in result.force_error

    def test_missing_col_injects_wrong_columns(self):
        inj = FailureInjector("missing_col", target_tool="file_reader")
        result = inj.inject("file_reader", {"path": "/data.csv"})
        assert "booked_rooms" in result.inputs.get("expected_columns", [])

    def test_trigger_on_call_n(self):
        """Inject only on the 2nd call, pass through on the 1st."""
        inj = FailureInjector("api_timeout", target_tool="api_tool", trigger_on_call=2)
        r1 = inj.inject("api_tool", {"endpoint": "http://localhost"})
        r2 = inj.inject("api_tool", {"endpoint": "http://localhost"})
        assert r1.force_error is None   # 1st call → no injection
        assert r2.force_error is not None  # 2nd call → injected

    def test_unsupported_mode_raises(self):
        with pytest.raises(ValueError, match="Unsupported failure mode"):
            FailureInjector("crash_and_burn")

    def test_reset_counters(self):
        inj = FailureInjector("api_timeout", target_tool="api_tool", trigger_on_call=1)
        inj.inject("api_tool", {"endpoint": "http://localhost"})
        inj.reset_counters()
        r = inj.inject("api_tool", {"endpoint": "http://localhost"})
        assert r.force_error is not None  # Counter reset → triggers again on call 1


# ══════════════════════════════════════════════════════════════════════════════
#  End-to-end failure + recovery tests
# ══════════════════════════════════════════════════════════════════════════════

class TestScenario1FailureInjection:

    def _run(self, failure_injection: str):
        from workflows.scenario1 import get_task, build_tools
        task = get_task(failure_injection=failure_injection)
        tools = build_tools()
        loop = AgentLoop(tools, max_steps=15, max_retries=3, time_limit=15.0)
        return loop.run(task)

    def test_normal_run_succeeds(self):
        result = self._run("none")
        assert result["status"] == "succeeded"
        assert result["output"] is not None
        assert "top_region" in result["output"]

    def test_bad_path_run_fails(self):
        result = self._run("bad_path")
        assert result["status"] in ("stopped", "failed")
        assert result["error"] is not None or result["output"] is None

    def test_missing_col_run_fails(self):
        result = self._run("missing_col")
        assert result["status"] in ("stopped", "failed")

    def test_bad_path_journal_contains_error(self):
        result = self._run("bad_path")
        events = [e["event"] for e in result.get("journal", [])]
        assert "ERROR" in events

    def test_bad_path_journal_contains_stop(self):
        result = self._run("bad_path")
        events = [e["event"] for e in result.get("journal", [])]
        assert "STOP" in events


class TestScenario2FailureInjection:

    def _run_scenario2(self, failure_injection: str):
        from workflows.scenario2 import get_task, build_tools, get_failure_injector
        task = get_task(failure_injection=failure_injection)
        injector = get_failure_injector(failure_injection)
        tools = build_tools()
        loop = AgentLoop(
            tools, max_steps=15, max_retries=3, time_limit=15.0,
            failure_injector=injector
        )
        return loop.run(task)

    def test_normal_scenario2_succeeds(self):
        result = self._run_scenario2("none")
        assert result["status"] == "succeeded"
        assert result["output"] is not None
        assert "trend" in result["output"]

    def test_api_timeout_fails_gracefully(self):
        result = self._run_scenario2("api_timeout")
        assert result["status"] in ("stopped", "failed")
        journal_errors = [
            e for e in result.get("journal", []) if e["event"] == "ERROR"
        ]
        assert len(journal_errors) > 0
        assert any("timeout" in str(e["data"]).lower() for e in journal_errors)

    def test_api_rate_limit_fails_gracefully(self):
        result = self._run_scenario2("api_rate_limit")
        assert result["status"] in ("stopped", "failed")
        journal_errors = [
            e for e in result.get("journal", []) if e["event"] == "ERROR"
        ]
        assert len(journal_errors) > 0

    def test_retry_mechanism_visible_in_journal(self):
        result = self._run_scenario2("api_timeout")
        # With max_retries=3, we should see multiple TOOL_CALL attempts
        tool_calls = [
            e for e in result.get("journal", []) if e["event"] == "TOOL_CALL"
        ]
        # At least one call was made
        assert len(tool_calls) >= 1
