"""
Scenario 2 – Tourism Indicator API Pull (Overnight Stays by Nationality).

Context:
    The Tunisian Ministry of Tourism needs a compact indicator snapshot of
    overnight-stay trends by foreign visitor nationality (European, Maghreb,
    North American, etc.), processed from either a live open-data API or
    the course's offline CSV fixture.

Input contract:
    Offline CSV: data_synthetic/overnight_stays_by_country.csv
    Columns: Nationality, Year, OvernightStays

Expected output:
    {
      "monthly_visitors": [...],
      "growth_rates": {...},
      "trend": "increasing" | "decreasing" | "stable",
      "peak_year": int,
      "total_by_year": {...}
    }

Failure injection:
    - "api_timeout"       → simulated timeout
    - "api_rate_limit"    → simulated HTTP 429

Constraints:
    max_steps=15, max_retries=3, time_limit=15s
"""

import os

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data_synthetic")
)
_OVERNIGHT_CSV = os.path.join(_DATA_DIR, "overnight_stays_by_country.csv")

# The mock/allow-listed endpoint we pretend to call
_MOCK_ENDPOINT = "http://localhost:8080/api/tourism/overnight-stays"


def get_task(failure_injection: str = "none", bad_csv: bool = False) -> dict:
    """
    Return the Scenario 2 task definition.

    failure_injection: "none" | "api_timeout" | "api_rate_limit"
    bad_csv: True → inject a nonexistent CSV path (FileNotFoundError)
    """
    offline_csv = _OVERNIGHT_CSV + "_DOES_NOT_EXIST" if bad_csv else _OVERNIGHT_CSV

    return {
        "id": "SCENARIO_2",
        "name": "Tunisia Overnight Stays Indicator Pull",
        "sector": "Tourism",
        "description": (
            "Pull overnight-stay indicator data, compute YoY growth rates, "
            "trend direction, and generate a chart-ready JSON summary."
        ),
        "required_objectives": ["api_tool"],
        "failure_injection": failure_injection,
        "tool_chain": [
            {
                "tool": "api_tool",
                "inputs": {
                    "endpoint": _MOCK_ENDPOINT,
                    "timeout_seconds": 8.0,
                    "offline_csv": offline_csv,
                },
                "requires": [],
                "input_from_results": {},
            },
        ],
        "success_criteria": {
            "output_fields": ["monthly_visitors", "growth_rates", "trend"],
            "trend_values": ["increasing", "decreasing", "stable"],
        },
        "constraints": {
            "max_steps": 15,
            "max_retries": 3,
            "time_limit_seconds": 15,
        },
    }


def get_failure_injector(failure_injection: str):
    from orchestrator.failure_injector import FailureInjector

    mode_map = {
        "none": "none",
        "api_timeout": "api_timeout",
        "api_rate_limit": "api_rate_limit",
    }
    mode = mode_map.get(failure_injection, "none")
    return FailureInjector(mode=mode, target_tool="api_tool")


def build_tools():
    from tools.api_tool import APITool
    return [APITool()]
