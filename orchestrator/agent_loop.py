"""
AgentLoop (Week 3) – fixed:
  - Passes retries_used + max_retries to Critic so retry works for all scenarios
  - Failure injector properly wired for both Scenario 1 and Scenario 2
  - DP cache integration
"""

from typing import Any, Dict, List, Optional

from orchestrator.run_manager import RunManager
from orchestrator.planner import BacktrackingPlanner, PlanningError
from orchestrator.executor import ToolExecutor, ExecutionRecord
from orchestrator.critic import Critic, CriticVerdict
from orchestrator.dp_cache import DPCache
from orchestrator.failure_injector import FailureInjector, InjectionResult
from tools.base_tool import BaseTool


class AgentLoop:
    def __init__(
        self,
        tools: List[BaseTool],
        max_steps: int = 15,
        max_retries: int = 3,
        time_limit: float = 15.0,
        dp_cache: Optional[DPCache] = None,
        failure_injector: Optional[FailureInjector] = None,
    ):
        self.tools_list = tools
        #tcoverti esm el tool lel format json ([tool1, tool2] → {"tool1": tool1, "tool2": tool2} ) 
        #bch t7assen fl speed ta3 el recherche
        self.tools_map: Dict[str, BaseTool] = {t.name: t for t in tools}
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.time_limit = time_limit
        self.dp_cache = dp_cache or DPCache()
        self.failure_injector = failure_injector or FailureInjector("none")

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        #ta3ti id lel task w tebda fl logging bl run manager
        task_id = task.get("id", "TASK_UNKNOWN")
        rm = RunManager(task_id)
        # initialisation ta3 les orchestrators
        planner = BacktrackingPlanner(
            self.tools_list, self.max_steps, self.max_retries, self.time_limit
        )
        executor = ToolExecutor(self.tools_map)
        critic = Critic(required_objectives=task.get("required_objectives", []))

        #meoire partagee bin el tools (memoization)
        accumulated_results: Dict[str, Any] = {}
        final_output: Optional[Dict] = None
        run_error: Optional[str] = None
        step_count = 0
        dp_hits_this_run = 0

        # ── PLAN ──────────────────────────────────────────────────────────────
        plan_step_id = rm.next_step_id()
        try:
            plan = planner.plan(task)
            rm.plan(plan_step_id, "planning", f"Plan has {len(plan)} steps")
        except PlanningError as exc:
            rm.error(plan_step_id, "planner", str(exc))
            stop_id = rm.next_step_id()
            rm.stop(stop_id, f"Planning failed: {exc}")
            rm.save_journal()
            return self._result(rm, None, planner, str(exc), dp_hits_this_run)

        # retry_counts tracks retries PER STEP INDEX
        retry_counts: Dict[int, int] = {}
        plan_index = 0

        #eceution bl step bl step
        while plan_index < len(plan):
            # ── Hard limits ────────────────────────────────────────────────
            if step_count >= self.max_steps:
                rm.stop(rm.next_step_id(), "Exceeded max_steps limit")
                break
            if rm.elapsed_seconds() >= self.time_limit:
                rm.stop(rm.next_step_id(), "Exceeded time_limit")
                break
            #tsavi el informations mta3 el steps
            step = plan[plan_index]
            tool_name: str = step["tool"]
            inputs: Dict = dict(step.get("inputs", {}))

            # Wire outputs from previous tools into inputs
            tool_chain_def = task.get("tool_chain", [])
            if plan_index < len(tool_chain_def):
                for key, source_key in tool_chain_def[plan_index].get(
                    "input_from_results", {}
                ).items():
                    if source_key in accumulated_results:
                        inputs[key] = accumulated_results[source_key]

            step_count += 1
            step_id = rm.next_step_id()
            retries_used = retry_counts.get(plan_index, 0)

            # ── DP Cache lookup ────────────────────────────────────────────
            fingerprint = accumulated_results.get("fingerprint", "")
            time_left = max(0.0, self.time_limit - rm.elapsed_seconds())
            retries_left = self.max_retries - retries_used
            dp_key = self.dp_cache.make_key(
                frozenset(accumulated_results.keys()),
                retries_left,
                time_left,
                fingerprint,
            )
            cached = self.dp_cache.get(dp_key)
            if cached is not None:
                dp_hits_this_run += 1
                rm.plan(step_id, tool_name, f"[DP HIT] reusing cached result")
                rm.result(step_id, tool_name, "[DP HIT] execution skipped")
                accumulated_results[tool_name] = cached
                if isinstance(cached, dict):
                    accumulated_results.update(cached)
                plan_index += 1
                continue

            # ── Failure injection ──────────────────────────────────────────
            injection: InjectionResult = self.failure_injector.inject(tool_name, inputs)
            inputs = injection.inputs

            rm.plan(step_id, tool_name,
                    f"Step {plan_index + 1}" + (f" [RETRY {retries_used}]" if retries_used > 0 else ""))
            rm.tool_call(step_id, tool_name, inputs)

            # ── Execute (or force injected error) ──────────────────────────
            if injection.force_error:
                record = ExecutionRecord(step_id, tool_name)
                record.error = injection.force_error
                record.inputs = inputs
            else:
                record = executor.execute(step_id, tool_name, inputs)

            # ── Observe ────────────────────────────────────────────────────
            if record.success:
                rm.result(step_id, tool_name, record.summary())
                accumulated_results[tool_name] = record.output
                if record.output:
                    accumulated_results.update(record.output)
                self.dp_cache.put(dp_key, record.output)
            else:
                rm.error(step_id, tool_name, record.error or "Unknown error")

            # ── Critique ───────────────────────────────────────────────────
            remaining = len(plan) - plan_index - 1
            decision = critic.evaluate(
                record,
                accumulated_results,
                remaining,
                retries_used=retries_used,
                max_retries=self.max_retries,
            )

            if decision.verdict == CriticVerdict.CONTINUE:
                plan_index += 1
                retry_counts.pop(plan_index - 1, None)  # reset retries for completed step

            elif decision.verdict == CriticVerdict.RETRY:
                retry_counts[plan_index] = retries_used + 1
                # Stay on same plan_index → loop retries this step

            elif decision.verdict == CriticVerdict.STOP_SUCCESS:
                final_output = (accumulated_results.get("report_generator")
                                or accumulated_results.get(tool_name)
                                or accumulated_results)
                rm.stop(rm.next_step_id(), "All objectives met – success")
                break

            elif decision.verdict == CriticVerdict.STOP_FAILURE:
                run_error = "; ".join(decision.reasons)
                rm.stop(rm.next_step_id(), f"Critic STOP_FAILURE – {run_error}")
                break

        # ── If loop ended without an explicit stop ─────────────────────────
        if rm.status == "running":
            if not run_error:
                final_output = (accumulated_results.get("report_generator")
                                or accumulated_results)
                rm.stop(rm.next_step_id(), "Run completed")
            else:
                rm.stop(rm.next_step_id(), f"Run ended with error: {run_error}")

        rm.save_journal()
        return self._result(rm, final_output, planner, run_error, dp_hits_this_run)

    def _result(self, rm, output, planner, error, dp_hits):
        return {
            "run_id": rm.run_id,
            "status": rm.status,
            "output": output,
            "journal": rm.journal,
            "planner_stats": planner.stats(),
            "dp_cache_stats": self.dp_cache.stats(),
            "dp_hits_this_run": dp_hits,
            "error": error,
            "elapsed_seconds": rm.elapsed_seconds(),
        }
