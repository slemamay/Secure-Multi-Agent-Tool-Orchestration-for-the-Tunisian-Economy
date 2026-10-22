"""
Unit tests for individual tools – schema validation, correct outputs, error handling.
Run with:  pytest tests/test_tools.py -v
"""

import os
import sys
import json
import pytest

# Make sure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.file_reader import FileReaderTool
from tools.kpi_calculator import KPICalculatorTool
from tools.report_generator import ReportGeneratorTool
from tools.base_tool import ToolExecutionError

DATA_CSV = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data_synthetic", "Scenario1.csv")
)
LOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "logs")
)


# ══════════════════════════════════════════════════════════════════════════════
#  FileReaderTool
# ══════════════════════════════════════════════════════════════════════════════

class TestFileReaderTool:
    def setup_method(self):
        self.tool = FileReaderTool()

    def test_happy_path_returns_rows(self):
        result = self.tool.execute({"path": DATA_CSV})
        assert result["row_count"] > 0
        assert "rows" in result
        assert "columns" in result
        assert "fingerprint" in result

    def test_correct_columns_detected(self):
        result = self.tool.execute({"path": DATA_CSV})
        assert "Region" in result["columns"]
        assert "OccupancyRate" in result["columns"]

    def test_file_not_found_raises(self):
        with pytest.raises(ToolExecutionError, match="File not found"):
            self.tool.execute({"path": DATA_CSV + "_NONEXISTENT"})

    def test_missing_column_raises(self):
        with pytest.raises(ToolExecutionError, match="Missing required columns"):
            self.tool.execute(
                {
                    "path": DATA_CSV,
                    "expected_columns": ["Region", "booked_rooms"],  # wrong column
                }
            )

    def test_security_blocks_outside_sandbox(self):
        from security.allow_list import PermissionError as _
        with pytest.raises(PermissionError):
            self.tool.execute({"path": "/etc/passwd"})

    def test_fingerprint_stable(self):
        r1 = self.tool.execute({"path": DATA_CSV})
        r2 = self.tool.execute({"path": DATA_CSV})
        assert r1["fingerprint"] == r2["fingerprint"]


# ══════════════════════════════════════════════════════════════════════════════
#  KPICalculatorTool
# ══════════════════════════════════════════════════════════════════════════════

class TestKPICalculatorTool:
    def setup_method(self):
        self.reader = FileReaderTool()
        self.calc = KPICalculatorTool()
        self.dataset = self.reader.execute({"path": DATA_CSV})

    def test_occupancy_rate_non_empty(self):
        result = self.calc.execute({"dataset": self.dataset})
        assert len(result["occupancy_rate_by_region"]) > 0

    def test_top_region_is_string(self):
        result = self.calc.execute({"dataset": self.dataset})
        assert isinstance(result["top_region"], str)
        assert len(result["top_region"]) > 0

    def test_occupancy_values_in_range(self):
        result = self.calc.execute({"dataset": self.dataset})
        for region, rate in result["occupancy_rate_by_region"].items():
            assert 0 <= rate <= 100, f"Rate out of range for {region}: {rate}"

    def test_alerts_list_returned(self):
        result = self.calc.execute({"dataset": self.dataset, "alert_threshold": 100.0})
        # All regions should trigger alert when threshold is 100%
        assert isinstance(result["alerts"], list)
        assert len(result["alerts"]) > 0

    def test_empty_dataset_raises(self):
        empty_ds = {"rows": [], "columns": [], "row_count": 0, "fingerprint": ""}
        with pytest.raises(ToolExecutionError, match="no rows"):
            self.calc.execute({"dataset": empty_ds})

    def test_custom_alert_threshold(self):
        result = self.calc.execute({"dataset": self.dataset, "alert_threshold": 50.0})
        for alert in result["alerts"]:
            assert alert["avg_occupancy_rate"] < 50.0


# ══════════════════════════════════════════════════════════════════════════════
#  ReportGeneratorTool
# ══════════════════════════════════════════════════════════════════════════════

class TestReportGeneratorTool:
    def setup_method(self):
        self.reader = FileReaderTool()
        self.calc = KPICalculatorTool()
        self.reporter = ReportGeneratorTool()
        dataset = self.reader.execute({"path": DATA_CSV})
        self.kpis = self.calc.execute({"dataset": dataset})

    def test_report_has_required_fields(self):
        report = self.reporter.execute({"kpis": self.kpis, "run_id": "TEST_001"})
        assert "occupancy_rate_by_region" in report
        assert "top_region" in report
        assert "alerts" in report
        assert "generated_at" in report

    def test_run_id_preserved(self):
        report = self.reporter.execute({"kpis": self.kpis, "run_id": "MY_RUN"})
        assert report["run_id"] == "MY_RUN"

    def test_report_written_to_file(self, tmp_path):
        out_file = str(tmp_path / "report.json")
        # Patch allow-list to allow tmp_path
        import security.allow_list as al
        original = set(al.ALLOWED_PATH_PREFIXES)
        al.ALLOWED_PATH_PREFIXES.add(str(tmp_path))
        try:
            self.reporter.execute(
                {"kpis": self.kpis, "run_id": "FILE_TEST", "output_path": out_file}
            )
            assert os.path.exists(out_file)
            with open(out_file) as f:
                data = json.load(f)
            assert "top_region" in data
        finally:
            al.ALLOWED_PATH_PREFIXES = original
