"""
Schema validation utilities.
Uses jsonschema if available, falls back to a lightweight built-in validator.
All tool inputs and outputs must pass validation before processing.
"""

from typing import Any, Dict, Optional

try:
    import jsonschema as _jschema
    _USE_JSONSCHEMA = True
except ImportError:
    _USE_JSONSCHEMA = False

# ── Re-usable JSON schemas ────────────────────────────────────────────────────

FILE_READER_INPUT_SCHEMA = {
    "type": "object",
    "required": ["path"],
    "additionalProperties": False,
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "delimiter": {"type": "string"},
        "expected_columns": {"type": "array", "items": {"type": "string"}},
    },
}

FILE_READER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["rows", "columns", "row_count"],
    "properties": {
        "rows": {"type": "array"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "row_count": {"type": "integer"},
        "fingerprint": {"type": "string"},
    },
}

KPI_CALCULATOR_INPUT_SCHEMA = {
    "type": "object",
    "required": ["dataset"],
    "properties": {
        "dataset": {"type": "object"},
        "alert_threshold": {"type": "number"},
    },
}

KPI_CALCULATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["occupancy_rate_by_region", "top_region", "alerts"],
    "properties": {
        "occupancy_rate_by_region": {"type": "object"},
        "top_region": {"type": "string"},
        "alerts": {"type": "array"},
        "bed_capacity_by_region": {"type": "object"},
        "establishments_by_region": {"type": "object"},
    },
}

REPORT_GENERATOR_INPUT_SCHEMA = {
    "type": "object",
    "required": ["kpis"],
    "properties": {
        "kpis": {"type": "object"},
        "run_id": {"type": "string"},
        "output_path": {"type": "string"},
    },
}

REPORT_GENERATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["occupancy_rate_by_region", "top_region", "alerts"],
    "properties": {
        "occupancy_rate_by_region": {"type": "object"},
        "top_region": {"type": "string"},
        "alerts": {"type": "array"},
        "bed_capacity_by_region": {"type": "object"},
        "establishments_by_region": {"type": "object"},
        "generated_at": {"type": "string"},
        "run_id": {"type": "string"},
    },
}

# ── Type mapping ──────────────────────────────────────────────────────────────
_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _lite_validate(data: Any, schema: Dict, path: str = "root") -> None:
    """Lightweight JSON schema validator (subset: type, required, additionalProperties, minLength)."""
    expected_type = schema.get("type")
    if expected_type and expected_type in _TYPE_MAP:
        py_type = _TYPE_MAP[expected_type]
        if not isinstance(data, py_type):
            raise SchemaValidationError(
                f"Schema validation failed: expected {expected_type} at '{path}', "
                f"got {type(data).__name__}"
            )

    if isinstance(data, dict):
        # required fields
        for req in schema.get("required", []):
            if req not in data:
                raise SchemaValidationError(
                    f"Schema validation failed: required field '{req}' missing at '{path}'"
                )
        # additionalProperties=False
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            extra = set(data.keys()) - allowed
            if extra:
                raise SchemaValidationError(
                    f"Schema validation failed: unexpected fields {extra} at '{path}'"
                )
        # validate child properties
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in data:
                _lite_validate(data[prop], prop_schema, path=f"{path}.{prop}")

    if isinstance(data, str) and "minLength" in schema:
        if len(data) < schema["minLength"]:
            raise SchemaValidationError(
                f"Schema validation failed: string at '{path}' is too short "
                f"(minLength={schema['minLength']})"
            )


def validate_schema(data: Any, schema: Dict) -> None:
    """Validate *data* against *schema*. Raises SchemaValidationError on failure."""
    if _USE_JSONSCHEMA:
        try:
            _jschema.validate(instance=data, schema=schema)
        except _jschema.ValidationError as exc:
            raise SchemaValidationError(
                f"Schema validation failed: {exc.message} "
                f"(path: {list(exc.absolute_path)})"
            ) from exc
    else:
        _lite_validate(data, schema)


class SchemaValidationError(ValueError):
    """Raised when a tool input or output fails schema validation."""

# ── API Tool schemas (Week 3) ─────────────────────────────────────────────────
API_TOOL_INPUT_SCHEMA = {
    "type": "object",
    "required": ["endpoint"],
    "additionalProperties": False,
    "properties": {
        "endpoint": {"type": "string", "minLength": 1},
        "timeout_seconds": {"type": "number"},
        "offline_csv": {"type": "string"},
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
