"""
RunManager – lifecycle management for orchestration runs.
"""

import json, os, threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_COUNTER_LOCK = threading.Lock()
_global_counter: int = 0

def _next_run_id() -> str:
    global _global_counter
    with _COUNTER_LOCK:
        _global_counter += 1
        return f"RUN_{_global_counter:03d}"


class RunManager:
    def __init__(self, task_id: str, log_dir: str = "logs"):
        self.run_id: str = _next_run_id()
        self.task_id: str = task_id
        self.log_dir: str = log_dir
        self._step_counter: int = 0
        self._journal: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._start_time = datetime.now(timezone.utc)
        self.status: str = "running"
        os.makedirs(log_dir, exist_ok=True)

    def next_step_id(self) -> str:
        with self._lock:
            self._step_counter += 1
            return f"STEP_{self._step_counter:02d}"

    def log_event(self, step_id: str, event_type: str,
                  data: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "run_id": self.run_id,
            "step_id": step_id,
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        with self._lock:
            self._journal.append(entry)

    def plan(self, step_id, tool_name, rationale=""):
        self.log_event(step_id, "PLAN", {"tool": tool_name, "rationale": rationale})

    def tool_call(self, step_id, tool_name, inputs):
        self.log_event(step_id, "TOOL_CALL",
                       {"tool": tool_name, "inputs": _redact(inputs)})

    def result(self, step_id, tool_name, summary):
        self.log_event(step_id, "RESULT", {"tool": tool_name, "summary": summary})

    def error(self, step_id, tool_name, message):
        self.log_event(step_id, "ERROR", {"tool": tool_name, "message": message})

    def stop(self, step_id, reason):
        self.log_event(step_id, "STOP", {"reason": reason})
        # ── Status is set ONLY here — based on the reason string ──────────
        reason_lower = reason.lower()
        if "success" in reason_lower or "objectives met" in reason_lower:
            self.status = "succeeded"
        else:
            self.status = "failed"   # covers: error, retries exceeded, timeout, etc.

    @property
    def journal(self):
        with self._lock:
            return list(self._journal)

    def elapsed_seconds(self):
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()

    def save_journal(self):
        path = os.path.join(self.log_dir, f"{self.run_id}.jsonl")
        with self._lock:
            with open(path, "w", encoding="utf-8") as fh:
                for entry in self._journal:
                    fh.write(json.dumps(entry) + "\n")
        return path

    def __repr__(self):
        return f"<RunManager {self.run_id} status={self.status}>"


_SENSITIVE_KEYS = {"password", "token", "secret", "key", "api_key", "auth"}

def _redact(d):
    if isinstance(d, dict):
        return {k: "***REDACTED***" if k.lower() in _SENSITIVE_KEYS
                else _redact(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_redact(i) for i in d]
    return d
