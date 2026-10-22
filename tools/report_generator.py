"""
ReportGeneratorTool – wraps KPIs into the canonical output JSON schema
and optionally persists the report to an allow-listed path.

Output schema (from Week 1):
{
  "occupancy_rate_by_region": {},
  "top_region": "",
  "alerts": [],
  "bed_capacity_by_region": {},
  "establishments_by_region": {},
  "generated_at": "",
  "run_id": ""
}
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from tools.base_tool import BaseTool, ToolExecutionError
from security.allow_list import assert_path_allowed
from security.validator import (
    REPORT_GENERATOR_INPUT_SCHEMA,
    REPORT_GENERATOR_OUTPUT_SCHEMA,
)


class ReportGeneratorTool(BaseTool):
    name = "report_generator"
    description = (
        "Formats KPIs into the canonical JSON dashboard schema. "
        "Optionally writes the report to an allow-listed output path."
    )
    input_schema = REPORT_GENERATOR_INPUT_SCHEMA
    output_schema = REPORT_GENERATOR_OUTPUT_SCHEMA
    is_mutating = True  # Writes a file – idempotent by run_id-keyed filename

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        kpis: Dict = inputs["kpis"]
        run_id: str = inputs.get("run_id", "UNKNOWN")
        output_path: str = inputs.get("output_path", "")

        # ── Build canonical report ────────────────────────────────────────────
        report: Dict[str, Any] = {
            "occupancy_rate_by_region": kpis.get("occupancy_rate_by_region", {}),
            "top_region": kpis.get("top_region", ""),
            "alerts": kpis.get("alerts", []),
            "bed_capacity_by_region": kpis.get("bed_capacity_by_region", {}),
            "establishments_by_region": kpis.get("establishments_by_region", {}),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
        }

        # ── Optional persistence ──────────────────────────────────────────────
        if output_path:
            assert_path_allowed(output_path)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            try:
                with open(output_path, "w", encoding="utf-8") as fh:
                    json.dump(report, fh, indent=2)
            except OSError as exc:
                raise ToolExecutionError(
                    self.name, f"Failed to write report: {exc}", recoverable=True
                ) from exc

        return report
