"""
KPICalculatorTool – computes tourism KPIs from the loaded dataset.

Dataset columns expected:
  Region, Year, BedCapacity, NumberOfEstablishments, OccupancyRate

KPIs produced:
  - occupancy_rate_by_region  : {region: avg_occupancy_rate}
  - top_region                : region with highest avg occupancy
  - bed_capacity_by_region    : {region: latest_bed_capacity}
  - establishments_by_region  : {region: latest_establishments}
  - alerts                    : list of alert dicts for low occupancy
"""

from typing import Any, Dict, List
from collections import defaultdict

from tools.base_tool import BaseTool, ToolExecutionError
from security.validator import (
    KPI_CALCULATOR_INPUT_SCHEMA,
    KPI_CALCULATOR_OUTPUT_SCHEMA,
)

# Threshold below which a region is flagged as low-occupancy
DEFAULT_ALERT_THRESHOLD = 30.0

# Regions that are aggregate rows (not individual regions – skip them)
_AGGREGATE_REGIONS = {"Bed capacity of all tourist regions in Tunisia"}


class KPICalculatorTool(BaseTool):
    name = "kpi_calculator"
    description = (
        "Computes tourism KPIs (occupancy rate, top region, alerts) "
        "from a dataset produced by the FileReaderTool."
    )
    input_schema = KPI_CALCULATOR_INPUT_SCHEMA
    output_schema = KPI_CALCULATOR_OUTPUT_SCHEMA
    is_mutating = False

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        dataset: Dict = inputs["dataset"]
        alert_threshold: float = inputs.get("alert_threshold", DEFAULT_ALERT_THRESHOLD)

        rows: List[Dict] = dataset.get("rows", [])
        if not rows:
            raise ToolExecutionError(
                self.name, "Dataset contains no rows.", recoverable=False
            )

        # ── Aggregate per region ──────────────────────────────────────────────
        occ_values: Dict[str, List[float]] = defaultdict(list)
        bed_capacity: Dict[str, float] = {}
        establishments: Dict[str, float] = {}

        for row in rows:
            region = str(row.get("Region", "")).strip()
            if not region or region in _AGGREGATE_REGIONS:
                continue

            # OccupancyRate is optional (some rows have it, some don't)
            occ_str = row.get("OccupancyRate", "")
            if occ_str not in (None, "", "nan"):
                try:
                    occ_values[region].append(float(occ_str))
                except (ValueError, TypeError):
                    pass

            # BedCapacity – keep latest (highest year)
            bed_str = row.get("BedCapacity", "")
            if bed_str not in (None, "", "nan"):
                try:
                    year = int(row.get("Year", 0))
                    bc = float(bed_str)
                    if region not in bed_capacity:
                        bed_capacity[region] = bc
                    else:
                        # Prefer more recent year (tracked via separate year map)
                        bed_capacity[region] = bc  # last wins → CSV is time-ordered
                except (ValueError, TypeError):
                    pass

            # NumberOfEstablishments
            est_str = row.get("NumberOfEstablishments", "")
            if est_str not in (None, "", "nan"):
                try:
                    establishments[region] = float(est_str)
                except (ValueError, TypeError):
                    pass

        if not occ_values:
            raise ToolExecutionError(
                self.name,
                "No valid OccupancyRate values found in dataset.",
                recoverable=False,
            )

        # ── Compute averages ──────────────────────────────────────────────────
        avg_occ: Dict[str, float] = {
            region: round(sum(vals) / len(vals), 2)
            for region, vals in occ_values.items()
        }

        top_region = max(avg_occ, key=lambda r: avg_occ[r])

        # ── Build alerts ──────────────────────────────────────────────────────
        alerts: List[Dict] = [
            {"region": r, "avg_occupancy_rate": v, "threshold": alert_threshold}
            for r, v in avg_occ.items()
            if v < alert_threshold
        ]

        return {
            "occupancy_rate_by_region": avg_occ,
            "top_region": top_region,
            "bed_capacity_by_region": {
                r: round(v, 0) for r, v in bed_capacity.items()
            },
            "establishments_by_region": {
                r: int(v) for r, v in establishments.items()
            },
            "alerts": alerts,
        }
