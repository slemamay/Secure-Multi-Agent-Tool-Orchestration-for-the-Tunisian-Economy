"""
BacktrackingPlanner – constrained search over feasible tool sequences.

State vector:
    step_index          : int            – index into the candidate tool list
    completed_objectives: frozenset[str] – tool names whose outputs are available
    retry_count         : int            – retries on the CURRENT step

The planner SIMULATES tool execution: as it recurses through the chain, it
tracks which tool names have been "completed" in the current branch, using
those to satisfy prerequisite checks (not live accumulated_results).

Pruning rules:
    P1. step_index >= max_steps
    P2. elapsed >= time_limit
    P3. retry_count >= max_retries
    P4. Required predecessor not yet completed in this branch
    P5. Same (step_index, objectives) already visited (dominance)
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional

from tools.base_tool import BaseTool


@dataclass(frozen=True)
class PlannerState:
    step_index: int
    completed_objectives: FrozenSet[str]
    retry_count: int


class BacktrackingPlanner:
    """Produces a feasible ordered plan (list of {tool, inputs} dicts)."""

    def __init__(
        self,
        available_tools: List[BaseTool],
        max_steps: int = 15,
        max_retries: int = 3,
        time_limit: float = 15.0,
    ):
        self.tools: Dict[str, BaseTool] = {t.name: t for t in available_tools}
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.time_limit = time_limit
        self.branches_explored: int = 0
        self.branches_pruned: int = 0
        self._visited: set = set()

    def plan(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.branches_explored = 0
        self.branches_pruned = 0
        self._visited = set()
        self._start_time = time.time()

        candidate_chain: List[Dict] = task.get("tool_chain", [])
        if not candidate_chain:
            raise PlanningError("Task has no tool_chain defined.")

        initial_state = PlannerState(
            step_index=0,
            completed_objectives=frozenset(),
            retry_count=0,
        )
        plan = self._backtrack(initial_state, candidate_chain)
        if plan is None:
            raise PlanningError(
                f"No feasible plan found after exploring "
                f"{self.branches_explored} branches "
                f"({self.branches_pruned} pruned)."
            )
        return plan

    def replan(
        self,
        task: Dict[str, Any],
        failed_at_step: int,
        partial_results: Dict[str, Any],
        reason: str,
    ) -> Optional[List[Dict[str, Any]]]:
        candidate_chain: List[Dict] = task.get("tool_chain", [])
        fallback_chain = task.get("fallback_chain", [])
        if fallback_chain and failed_at_step == 0:
            return fallback_chain
        remaining = candidate_chain[failed_at_step + 1:]
        if not remaining:
            return None
        # Simulate the already-completed tools as available
        done = frozenset(partial_results.keys())
        state = PlannerState(
            step_index=0,
            completed_objectives=done,
            retry_count=0,
        )
        self._start_time = time.time()
        self._visited = set()
        return self._backtrack(state, remaining)

    def _backtrack(
        self,
        state: PlannerState,
        chain: List[Dict],
    ) -> Optional[List[Dict[str, Any]]]:

        # Base case
        if state.step_index >= len(chain):
            return []

        elapsed = time.time() - self._start_time

        # Pruning
        if state.step_index >= self.max_steps:
            self.branches_pruned += 1
            return None  # P1
        if elapsed >= self.time_limit:
            self.branches_pruned += 1
            return None  # P2
        if state.retry_count >= self.max_retries:
            self.branches_pruned += 1
            return None  # P3

        state_key = (state.step_index, state.completed_objectives)
        if state_key in self._visited:
            self.branches_pruned += 1
            return None  # P5
        self._visited.add(state_key)

        self.branches_explored += 1

        step_def = chain[state.step_index]
        tool_name: str = step_def["tool"]
        tool = self.tools.get(tool_name)

        if tool is None:
            self.branches_pruned += 1
            return None  # Tool not registered

        # P4: Check that required predecessors have been simulated-completed
        requires: List[str] = step_def.get("requires", [])
        if not all(req in state.completed_objectives for req in requires):
            self.branches_pruned += 1
            return None  # P4

        # Build inputs template
        inputs = dict(step_def.get("inputs", {}))
        # Note: actual input_from_results wiring happens at execution time

        plan_step = {"tool": tool_name, "inputs": inputs}

        # Recurse with this tool "completed" in simulation
        next_objectives = state.completed_objectives | frozenset([tool_name])
        next_state = PlannerState(
            step_index=state.step_index + 1,
            completed_objectives=next_objectives,
            retry_count=0,
        )
        sub_plan = self._backtrack(next_state, chain)
        if sub_plan is not None:
            return [plan_step] + sub_plan

        # Retry this step
        retry_state = PlannerState(
            step_index=state.step_index,
            completed_objectives=state.completed_objectives,
            retry_count=state.retry_count + 1,
        )
        return self._backtrack(retry_state, chain)

    def stats(self) -> Dict[str, Any]:
        return {
            "branches_explored": self.branches_explored,
            "branches_pruned": self.branches_pruned,
            "pruning_rate": round(
                self.branches_pruned / max(self.branches_explored, 1), 3
            ),
        }


class PlanningError(RuntimeError):
    """Raised when the planner cannot find a feasible plan."""
