"""
Scenario 1 – Local Tourism Dataset KPI Dashboard.

Context:
    The Tunisian National Tourism Office (ONTT) needs a daily KPI dashboard
    from the regional hotel statistics CSV. The Planner reads the file,
    computes KPIs, and generates a JSON report.

Input contract:
    File: data_synthetic/Scenario1.csv
    Columns: Region, Year, BedCapacity, NumberOfEstablishments, OccupancyRate

Expected output:
    {
      "occupancy_rate_by_region": {...},
      "top_region": "...",
      "alerts": [...],
      "bed_capacity_by_region": {...},
      "establishments_by_region": {...},
      "generated_at": "...",
      "run_id": "..."
    }

Constraints:
    max_steps: 15, max_retries: 3, time_limit: 15s
    Only allow-listed file paths; input must pass schema validation.

Validation rule (Critic):
    - occupancy_rate_by_region must be non-empty
    - top_region must be a non-empty string
    - KPI values must be finite numbers
"""

import os

# Resolve data path relative to this file
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data_synthetic")
_SCENARIO1_CSV = os.path.normpath(os.path.join(_DATA_DIR, "Scenario1.csv"))
_LOG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "logs"))


def get_task(failure_injection: str = "none") -> dict:
    """
    Return the Scenario 1 task definition.

    failure_injection: one of
        "none"          – normal run
        "bad_path"      – inject wrong file path (file not found)
        "missing_col"   – inject wrong expected_columns (column missing)
    """
    csv_path = _SCENARIO1_CSV
    expected_columns = ["Region", "Year", "BedCapacity", "OccupancyRate"]

    # ── Failure injections ────────────────────────────────────────────────────
    if failure_injection == "bad_path":
        csv_path = _SCENARIO1_CSV + "_DOES_NOT_EXIST"
    elif failure_injection == "missing_col":
        expected_columns = ["Region", "Year", "booked_rooms", "total_rooms"]  # wrong cols

    output_path = os.path.join(_LOG_DIR, "scenario1_report.json")

    return {
        "id": "SCENARIO_1",
        "name": "Tunisian Tourism KPI Dashboard",
        "sector": "Tourism",
        "description": (
            "Read regional hotel statistics, compute occupancy KPIs, "
            "and generate a JSON dashboard report for the ONTT."
        ),
        "required_objectives": ["report_generator"],
        "tool_chain": [
            {
                "tool": "file_reader",
                "inputs": {
                    "path": csv_path,
                    "delimiter": ",",
                    "expected_columns": expected_columns,
                },
                "requires": [],
                "input_from_results": {},
            },
            {
                "tool": "kpi_calculator",
                "inputs": {"alert_threshold": 30.0},
                "requires": ["file_reader"],
                "input_from_results": {"dataset": "file_reader"},
            },
            {
                "tool": "report_generator",
                "inputs": {"output_path": output_path},
                "requires": ["kpi_calculator"],
                "input_from_results": {
                    "kpis": "kpi_calculator",
                },
            },
        ],
        "success_criteria": {
            "output_fields": [
                "occupancy_rate_by_region",
                "top_region",
                "alerts",
            ],
            "non_empty": ["occupancy_rate_by_region", "top_region"],
        },
        "constraints": {
            "max_steps": 15,
            "max_retries": 3,
            "time_limit_seconds": 15,
        },
    }


def build_tools():
    """Return a list of tool instances required for Scenario 1."""
    from tools.file_reader import FileReaderTool
    from tools.kpi_calculator import KPICalculatorTool
    from tools.report_generator import ReportGeneratorTool

    return [FileReaderTool(), KPICalculatorTool(), ReportGeneratorTool()]
