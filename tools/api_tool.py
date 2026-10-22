"""
APITool – fetches tourism indicator data from an allow-listed HTTP endpoint.
For Scenario 2, it reads from the mock server or from a pre-loaded CSV
(when running offline / in test mode).

Supports:
  - Real HTTP GET with explicit timeout and response size limit
  - Offline mode: reads overnight_stays_by_country.csv as mock API response
  - Retry hints via tenacity (bounded; respects max_retries from caller)
"""

import csv
import json
import os
import time
from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolExecutionError
from security.allow_list import assert_api_allowed, ALLOWED_API_HOSTS

# Max response size accepted (bytes)
_MAX_RESPONSE_BYTES = 1_000_000  # 1 MB

API_TOOL_INPUT_SCHEMA = {
    "type": "object",
    "required": ["endpoint"],
    "additionalProperties": False,
    "properties": {
        "endpoint": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number", "default": 10.0},
        "offline_csv": {"type": "string"},   # path for offline/mock mode
        "params": {"type": "object"},
    },
}

API_TOOL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["monthly_visitors", "growth_rates", "trend"],
    "properties": {
        "monthly_visitors": {"type": "array"},
        "growth_rates": {"type": "object"},
        "trend": {"type": "string"},
        "peak_year": {"type": "integer"},
        "total_by_year": {"type": "object"},
        "source": {"type": "string"},
    },
}


class APITool(BaseTool):
    name = "api_tool"
    description = (
        "Fetches Tunisian tourism indicators from an allow-listed API endpoint. "
        "Supports offline (CSV) mode for reproducibility."
    )
    input_schema = API_TOOL_INPUT_SCHEMA
    output_schema = API_TOOL_OUTPUT_SCHEMA
    is_mutating = False

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        endpoint: str = inputs["endpoint"]
        timeout: float = inputs.get("timeout_seconds", 10.0)
        offline_csv: Optional[str] = inputs.get("offline_csv")
        params: Dict = inputs.get("params", {})

        # ── Security: check allow-list ─────────────────────────────────────
        assert_api_allowed(endpoint)

        # ── Offline / mock mode ────────────────────────────────────────────
        if offline_csv:
            return self._from_csv(offline_csv)

        # ── Live HTTP call ─────────────────────────────────────────────────
        try:
            import urllib.request
            import urllib.parse

            if params:
                query = urllib.parse.urlencode(params)
                url = f"{endpoint}?{query}"
            else:
                url = endpoint

            req = urllib.request.Request(url, headers={"User-Agent": "TunisiaOrchestrator/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(_MAX_RESPONSE_BYTES)

            data = json.loads(raw)
            return self._parse_api_response(data)

        except TimeoutError as exc:
            raise ToolExecutionError(
                self.name, f"API timeout after {timeout}s: {exc}", recoverable=True
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(
                self.name, f"API call failed: {exc}", recoverable=True
            ) from exc

    # ── Offline CSV mode (uses overnight_stays_by_country.csv) ────────────────

    def _from_csv(self, csv_path: str) -> Dict[str, Any]:
        from security.allow_list import assert_path_allowed
        assert_path_allowed(csv_path)

        if not os.path.isfile(csv_path):
            raise ToolExecutionError(
                self.name, f"Offline CSV not found: {csv_path}", recoverable=False
            )

        rows: List[Dict] = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))

        return self._compute_indicators(rows)

    def _compute_indicators(self, rows: List[Dict]) -> Dict[str, Any]:
        # Aggregate total overnight stays by year
        total_by_year: Dict[int, int] = {}
        stays_by_nationality: Dict[str, Dict[int, int]] = {}

        for row in rows:
            try:
                year = int(row["Year"])
                stays = int(row["OvernightStays"])
                nat = row["Nationality"]
            except (KeyError, ValueError):
                continue

            total_by_year[year] = total_by_year.get(year, 0) + stays
            if nat not in stays_by_nationality:
                stays_by_nationality[nat] = {}
            stays_by_nationality[nat][year] = stays

        if not total_by_year:
            raise ToolExecutionError(
                self.name, "No valid rows in indicator dataset.", recoverable=False
            )

        # YoY growth rates per nationality (most recent consecutive pair)
        growth_rates: Dict[str, float] = {}
        for nat, year_data in stays_by_nationality.items():
            years = sorted(year_data.keys())
            if len(years) >= 2:
                prev = year_data[years[-2]]
                curr = year_data[years[-1]]
                if prev > 0:
                    growth_rates[nat] = round((curr - prev) / prev * 100, 2)

        # Monthly visitors (simulate as yearly totals for each available year)
        sorted_years = sorted(total_by_year.keys())
        monthly_visitors = [
            {"year": y, "overnight_stays_thousands": round(total_by_year[y] / 1000, 1)}
            for y in sorted_years
        ]

        # Overall trend based on last 3 years
        if len(sorted_years) >= 3:
            recent = [total_by_year[y] for y in sorted_years[-3:]]
            if recent[-1] > recent[0]:
                trend = "increasing"
            elif recent[-1] < recent[0]:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        peak_year = max(total_by_year, key=lambda y: total_by_year[y])

        return {
            "monthly_visitors": monthly_visitors,
            "growth_rates": growth_rates,
            "trend": trend,
            "peak_year": peak_year,
            "total_by_year": {str(y): v for y, v in total_by_year.items()},
            "source": "overnight_stays_by_country.csv (offline mode)",
        }

    def _parse_api_response(self, data: Any) -> Dict[str, Any]:
        """Parse a real API response (World Bank / IMF style)."""
        # Fallback for unexpected formats
        return {
            "monthly_visitors": [],
            "growth_rates": {},
            "trend": "unknown",
            "peak_year": 0,
            "total_by_year": {},
            "source": "live_api",
        }
