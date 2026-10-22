"""
Safety tests – verify that the allow-list blocks unsafe tool calls.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.allow_list import (
    is_path_allowed,
    is_api_allowed,
    assert_path_allowed,
    assert_api_allowed,
)
from tools.file_reader import FileReaderTool


class TestAllowList:

    def test_sandbox_path_allowed(self):
        data_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data_synthetic", "x.csv")
        )
        assert is_path_allowed(data_path) is True

    def test_system_path_blocked(self):
        assert is_path_allowed("/etc/passwd") is False

    def test_home_dir_blocked(self):
        assert is_path_allowed(os.path.expanduser("~/.ssh/id_rsa")) is False

    def test_path_traversal_blocked(self):
        data_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data_synthetic", "..", "..", "etc", "passwd")
        )
        assert is_path_allowed(data_path) is False

    def test_allowed_api_host(self):
        assert is_api_allowed("https://data.worldbank.org/indicator/EN.ATM.CO2E.KT") is True

    def test_blocked_api_host(self):
        assert is_api_allowed("https://evil.com/exfiltrate") is False
        assert is_api_allowed("http://internal-corp-db.local/secrets") is False

    def test_assert_path_raises_for_blocked(self):
        with pytest.raises(PermissionError, match="allow-list"):
            assert_path_allowed("/tmp/evil.csv")

    def test_assert_api_raises_for_blocked(self):
        with pytest.raises(PermissionError, match="allow-list"):
            assert_api_allowed("https://unknown-service.io/data")


class TestToolSafetyBlocking:

    def test_file_reader_blocks_system_path(self):
        tool = FileReaderTool()
        with pytest.raises(PermissionError):
            tool.execute({"path": "/etc/hosts"})

    def test_file_reader_blocks_traversal(self):
        tool = FileReaderTool()
        with pytest.raises(PermissionError):
            tool.execute({"path": "../../etc/passwd"})
