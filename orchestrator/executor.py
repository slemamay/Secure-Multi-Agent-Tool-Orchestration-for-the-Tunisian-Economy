"""
ToolExecutor – validates inputs/outputs against schemas, calls the tool,
and returns a structured execution record.
"""

import time
from typing import Any, Dict, Optional

from tools.base_tool import BaseTool, ToolExecutionError
from security.validator import validate_schema, SchemaValidationError


class ExecutionRecord:
    """Captures the full context of a single tool invocation."""

    def __init__(self, step_id: str, tool_name: str):
        self.step_id = step_id
        self.tool_name = tool_name
        self.inputs: Dict = {}
        self.output: Optional[Dict] = None
        self.error: Optional[str] = None
        self.input_valid: bool = False
        self.output_valid: bool = False
        self.duration_ms: float = 0.0
        self.success: bool = False

    def summary(self) -> str:
        if self.success:
            keys = list((self.output or {}).keys())
            return f"OK - output keys: {keys}"
        return f"FAILED - {self.error}"


class ToolExecutor:
    """
    Wraps tool execution with:
    - Input schema validation
    - Timed execution
    - Output schema validation
    - Structured ExecutionRecord return
    """

    def __init__(self, tools: Dict[str, BaseTool]):
        self.tools = tools
    #trunni tool wa7da
    def execute(
        self, step_id: str, tool_name: str, inputs: Dict[str, Any]
    ) -> ExecutionRecord:
        record = ExecutionRecord(step_id, tool_name)
        record.inputs = inputs

        tool = self.tools.get(tool_name)
        if tool is None:
            record.error = f"Tool '{tool_name}' is not registered."
            return record

        # ── Input schema validation ───────────────────────────────────────────
        try:
            validate_schema(inputs, tool.input_schema)
            record.input_valid = True
        except SchemaValidationError as exc:
            record.error = f"Input validation failed: {exc}"
            return record

        # ── Execute tool ──────────────────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            output = tool.execute(inputs)
        except ToolExecutionError as exc:
            record.error = str(exc)
            record.duration_ms = (time.perf_counter() - t0) * 1000
            return record
        except Exception as exc:
            record.error = f"Unexpected error in {tool_name}: {exc}"
            record.duration_ms = (time.perf_counter() - t0) * 1000
            return record
        finally:
            record.duration_ms = (time.perf_counter() - t0) * 1000

        # ── Output schema validation ──────────────────────────────────────────
        try:
            if tool.output_schema:
                validate_schema(output, tool.output_schema)
            record.output_valid = True
        except SchemaValidationError as exc:
            record.error = f"Output validation failed: {exc}"
            return record

        record.output = output
        record.success = True
        return record
