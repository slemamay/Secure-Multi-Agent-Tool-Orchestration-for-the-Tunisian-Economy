"""
Base tool contract: every tool must subclass BaseTool and implement execute().
The executor validates inputs/outputs against the declared JSON schemas.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseTool(ABC):
    """Abstract base for all tools in the orchestration system."""

    # Subclasses must declare these
    name: str = "base_tool"
    description: str = ""
    input_schema: Dict = {}
    output_schema: Dict = {}
    is_mutating: bool = False   # True = has side effects; affects retry strategy

    @abstractmethod
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the tool with validated *inputs* and return a structured result.
        Raises ToolExecutionError on failure.
        """
        ...

    def __repr__(self) -> str:
        return f"<Tool:{self.name}>"


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails during execution (not a schema error)."""

    def __init__(self, tool_name: str, message: str, recoverable: bool = True):
        super().__init__(f"[{tool_name}] {message}")
        self.tool_name = tool_name
        self.recoverable = recoverable  # If True, the planner may retry/backtrack
