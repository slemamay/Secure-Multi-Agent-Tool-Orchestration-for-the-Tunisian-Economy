"""
Unit tests for schema validation layer.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.validator import validate_schema, SchemaValidationError
from security.validator import (
    FILE_READER_INPUT_SCHEMA,
    KPI_CALCULATOR_INPUT_SCHEMA,
    REPORT_GENERATOR_INPUT_SCHEMA,
)


class TestSchemaValidation:

    def test_valid_file_reader_input(self):
        validate_schema({"path": "/data/file.csv"}, FILE_READER_INPUT_SCHEMA)

    def test_missing_required_path_raises(self):
        with pytest.raises(SchemaValidationError):
            validate_schema({}, FILE_READER_INPUT_SCHEMA)

    def test_extra_field_rejected(self):
        with pytest.raises(SchemaValidationError):
            validate_schema(
                {"path": "/data/file.csv", "unknown_field": True},
                FILE_READER_INPUT_SCHEMA,
            )

    def test_wrong_type_raises(self):
        with pytest.raises(SchemaValidationError):
            validate_schema({"path": 123}, FILE_READER_INPUT_SCHEMA)

    def test_valid_kpi_input(self):
        validate_schema(
            {"dataset": {"rows": [], "columns": [], "row_count": 0}},
            KPI_CALCULATOR_INPUT_SCHEMA,
        )

    def test_valid_report_input(self):
        validate_schema(
            {"kpis": {"occupancy_rate_by_region": {}, "top_region": "A", "alerts": []}},
            REPORT_GENERATOR_INPUT_SCHEMA,
        )

    def test_empty_path_rejected(self):
        with pytest.raises(SchemaValidationError):
            validate_schema({"path": ""}, FILE_READER_INPUT_SCHEMA)
