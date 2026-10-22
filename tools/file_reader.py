"""
FileReaderTool – reads a CSV file from an allow-listed path and returns
a structured dataset dict that downstream tools can consume.
"""

import csv
import hashlib
import os
from typing import Any, Dict, List

from tools.base_tool import BaseTool, ToolExecutionError
from security.allow_list import assert_path_allowed
from security.validator import (
    FILE_READER_INPUT_SCHEMA,
    FILE_READER_OUTPUT_SCHEMA,
)


class FileReaderTool(BaseTool):
    name = "file_reader"
    description = (
        "Reads a CSV file from an allow-listed sandbox path. "
        "Validates that required columns are present before returning the dataset."
    )
    input_schema = FILE_READER_INPUT_SCHEMA
    output_schema = FILE_READER_OUTPUT_SCHEMA
    is_mutating = False

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        path: str = inputs["path"]
        delimiter: str = inputs.get("delimiter", ",")
        expected_columns: List[str] = inputs.get("expected_columns", [])

        # ── Security check ────────────────────────────────────────────────────
        assert_path_allowed(path)

        # ── Existence check ───────────────────────────────────────────────────
        if not os.path.isfile(path):
            raise ToolExecutionError(
                self.name, f"File not found: '{path}'", recoverable=False
            )

        # ── Read CSV ──────────────────────────────────────────────────────────
        rows: List[Dict] = []
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh, delimiter=delimiter)
                columns = list(reader.fieldnames or [])
                for row in reader:
                    rows.append(dict(row))
        except Exception as exc:
            raise ToolExecutionError(
                self.name, f"Failed to read CSV: {exc}", recoverable=False
            ) from exc

        # ── Column validation ─────────────────────────────────────────────────
        if expected_columns:
            missing = [c for c in expected_columns if c not in columns]
            if missing:
                raise ToolExecutionError(
                    self.name,
                    f"Missing required columns: {missing}. "
                    f"Available columns: {columns}",
                    recoverable=False,
                )

        # ── Compute content fingerprint (for DP memoization in Week 3) ───────
        raw = "".join(str(r) for r in rows)
        fingerprint = hashlib.md5(raw.encode()).hexdigest()

        return {
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
            "fingerprint": fingerprint,
        }
