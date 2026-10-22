"""
FailureInjector – testing mode that injects deterministic failures
into tool calls to validate the recovery and fallback mechanisms.

Supported failure modes (per Week 2/3 requirements):
    "bad_path"          → FileReaderTool receives a nonexistent path
    "missing_col"       → FileReaderTool sees wrong expected columns
    "api_timeout"       → APITool raises a simulated timeout
    "api_rate_limit"    → APITool raises HTTP 429
    "division_by_zero"  → KPICalculatorTool receives empty dataset
    "none"              → No injection (pass-through)

The injector is a stateless transformer: it receives a (tool_name, inputs)
pair and returns a (possibly modified) inputs dict along with an optional
override error to raise immediately.
"""

from typing import Any, Dict, Optional, Tuple


class InjectionResult:
    def __init__(
        self,
        inputs: Dict[str, Any],
        force_error: Optional[str] = None,
    ):
        self.inputs = inputs
        self.force_error = force_error  # If set, raise this as ToolExecutionError


class FailureInjector:
    """
    Wraps around the executor's tool dispatch to inject failures.

    Args:
        mode: one of the supported failure mode strings
        target_tool: if set, only inject failure for this tool name
        trigger_on_call: inject on the Nth call (1-based); None = always
    """

    SUPPORTED_MODES = {
        "none",
        "bad_path",
        "missing_col",
        "api_timeout",
        "api_rate_limit",
        "division_by_zero",
    }

    def __init__(
        self,
        mode: str = "none",
        target_tool: Optional[str] = None,
        trigger_on_call: Optional[int] = None,
    ):
        if mode not in self.SUPPORTED_MODES:
            raise ValueError(f"Unsupported failure mode: {mode!r}. "
                             f"Choose from {self.SUPPORTED_MODES}")
        self.mode = mode
        self.target_tool = target_tool
        self.trigger_on_call = trigger_on_call
        self._call_count: Dict[str, int] = {}

    def inject(self, tool_name: str, inputs: Dict[str, Any]) -> InjectionResult:
        """
        Return an InjectionResult with possibly modified inputs or a forced error.
        If mode is 'none' or this tool is not targeted, returns inputs unchanged.
        """
        if self.mode == "none":
            return InjectionResult(inputs)

        if self.target_tool and tool_name != self.target_tool:
            return InjectionResult(inputs)

        # Track call count per tool
        self._call_count[tool_name] = self._call_count.get(tool_name, 0) + 1
        if self.trigger_on_call is not None:
            if self._call_count[tool_name] != self.trigger_on_call:
                return InjectionResult(inputs)

        return self._apply(tool_name, inputs)

    def _apply(self, tool_name: str, inputs: Dict[str, Any]) -> InjectionResult:
        modified = dict(inputs)

        if self.mode == "bad_path":
            modified["path"] = "/nonexistent/injected/failure/data.csv"
            return InjectionResult(modified)

        if self.mode == "missing_col":
            modified["expected_columns"] = ["booked_rooms", "total_rooms", "nights_stayed"]
            return InjectionResult(modified)

        if self.mode == "api_timeout":
            return InjectionResult(
                modified,
                force_error=(
                    f"[{tool_name}] Simulated API timeout "
                    "(INJECTED for testing — not a real network error)"
                ),
            )

        if self.mode == "api_rate_limit":
            return InjectionResult(
                modified,
                force_error=(
                    f"[{tool_name}] Simulated HTTP 429 Too Many Requests "
                    "(INJECTED for testing)"
                ),
            )

        if self.mode == "division_by_zero":
            # Force an empty dataset → KPICalculator raises on empty rows
            modified["dataset"] = {"rows": [], "columns": [], "row_count": 0, "fingerprint": ""}
            return InjectionResult(modified)

        return InjectionResult(inputs)

    def reset_counters(self) -> None:
        self._call_count.clear()

    def describe(self) -> str:
        return (
            f"FailureInjector(mode={self.mode!r}, "
            f"target={self.target_tool!r}, "
            f"trigger_on_call={self.trigger_on_call})"
        )
