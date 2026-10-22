"""
Security: Allow-list enforcement for file paths and API endpoints.
No tool call is permitted unless it passes these checks.
"""

import os
from pathlib import Path
from typing import Set

# ── Allowed file-system paths ─────────────────────────────────────────────────
# Only paths inside the project sandbox are permitted.
_BASE_DIR = Path(__file__).resolve().parent.parent

ALLOWED_PATH_PREFIXES: Set[str] = {
    str(_BASE_DIR / "data_synthetic"),
    str(_BASE_DIR / "logs"),
    str(_BASE_DIR / "docs"),
}

# ── Allowed API hostnames (Scenario 2 – not used in Week 2) ──────────────────
ALLOWED_API_HOSTS: Set[str] = {
    "data.worldbank.org",
    "api.worldbank.org",
    "comtrade.un.org",
    "open-meteo.com",
    "localhost",          # mock server in tests
    "127.0.0.1",
}


def is_path_allowed(path: str) -> bool:
    """Return True only if *path* resolves to within an allowed prefix."""
    try:
        resolved = str(Path(path).resolve())
    except Exception:
        return False
    return any(resolved.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def is_api_allowed(url: str) -> bool:
    """Return True only if the URL's hostname is allow-listed."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ""
        return host in ALLOWED_API_HOSTS
    except Exception:
        return False


def assert_path_allowed(path: str) -> None:
    """Raise PermissionError if path is not allow-listed."""
    if not is_path_allowed(path):
        raise PermissionError(
            f"[SECURITY] Path '{path}' is outside the allow-list. "
            "Only sandbox paths are permitted."
        )


def assert_api_allowed(url: str) -> None:
    """Raise PermissionError if URL is not allow-listed."""
    if not is_api_allowed(url):
        raise PermissionError(
            f"[SECURITY] API host in '{url}' is not allow-listed."
        )
