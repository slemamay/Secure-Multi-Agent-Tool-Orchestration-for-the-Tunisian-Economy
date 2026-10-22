"""
Critic – evaluates ExecutionRecords for correctness and safety.

Fixed in Week 3:
- Retry is now driven by retry_budget (passed from agent loop), not remaining_steps.
  This ensures retries happen even for single-tool scenarios (Scenario 2).
- STOP_FAILURE only when retry budget is also exhausted.
"""

from typing import Any, Dict, List, Optional
from orchestrator.executor import ExecutionRecord


class CriticVerdict:
    CONTINUE = "CONTINUE"
    STOP_SUCCESS = "STOP_SUCCESS"
    STOP_FAILURE = "STOP_FAILURE"
    RETRY = "RETRY"


class Critic:
    def __init__(self, required_objectives: Optional[List[str]] = None):
        self.required_objectives = required_objectives or []
        self._safety_violations: List[str] = []

    def evaluate(
        self,
        record: ExecutionRecord,
        accumulated_results: Dict[str, Any],
        remaining_steps: int,
        retries_used: int = 0,
        max_retries: int = 3,
    ) -> "CriticDecision":

        reasons: List[str] = []

        # ── 1. Execution failure ──────────────────────────────────────────────
        #tchouf ken el tool 3amlet echec
        if not record.success:
            #tloggi el reason ta3 l echec
            reasons.append(f"Tool {record.tool_name} failed: {record.error}")
            # Retry if budget allows — regardless of remaining_steps
            if retries_used < max_retries:
                return CriticDecision(CriticVerdict.RETRY, reasons, safety_ok=True)
            else:
                return CriticDecision(CriticVerdict.STOP_FAILURE, reasons, safety_ok=True)

        # ── 2. Output validation ──────────────────────────────────────────────
        if not record.output_valid:
            reasons.append("Output schema validation failed.")
            return CriticDecision(CriticVerdict.STOP_FAILURE, reasons, safety_ok=True)

        # ── 3. Safety checks ──────────────────────────────────────────────────
        safety_ok, safety_reason = self._check_safety(record)
        if not safety_ok:
            self._safety_violations.append(safety_reason)
            reasons.append(f"SAFETY VIOLATION: {safety_reason}")
            return CriticDecision(CriticVerdict.STOP_FAILURE, reasons, safety_ok=False)

        # ── 4. Check objectives ───────────────────────────────────────────────
        all_met = all(obj in accumulated_results for obj in self.required_objectives)
        #ken les objectives lkol validethom t7ot succes 7atta ken el steps wfeww
        if remaining_steps == 0:
            if all_met:
                reasons.append("All objectives met.")
                return CriticDecision(CriticVerdict.STOP_SUCCESS, reasons, safety_ok=True)
            else: #snn echec
                unmet = [o for o in self.required_objectives if o not in accumulated_results]
                reasons.append(f"Objectives not met: {unmet}")
                return CriticDecision(CriticVerdict.STOP_FAILURE, reasons, safety_ok=True)

        reasons.append(f"Step {record.step_id} OK — continuing.")
        return CriticDecision(CriticVerdict.CONTINUE, reasons, safety_ok=True)

    def _check_safety(self, record: ExecutionRecord):
        output = record.output or {}
        for key, val in output.items():
            if isinstance(val, str) and val.startswith("/") and ".." in val:
                return False, f"Path traversal in output key '{key}'"
        return True, ""
    #traja3 lista feha el mechekel li detectee lkol
    @property 
    #@property lets you use a method like a variable (e.g., obj.value instead of obj.get_value()).
    # We use it to keep data safe and controlled while still having clean, simple access.
    #Because it lets you control access to your data without making your code messy.
    def safety_violations(self) -> List[str]:
        return list(self._safety_violations)

#class li nsajlou feha el decision final
class CriticDecision:
    def __init__(self, verdict: str, reasons: List[str], safety_ok: bool):
        self.verdict = verdict
        self.reasons = reasons
        self.safety_ok = safety_ok

    def __repr__(self):
        return f"<CriticDecision verdict={self.verdict} safety={self.safety_ok}>"
