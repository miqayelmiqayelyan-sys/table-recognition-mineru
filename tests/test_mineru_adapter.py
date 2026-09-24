from pathlib import Path

import pytest

from table_recognition_mineru.config import MinerUConfig
from table_recognition_mineru.mineru_adapter import MinerUAdapter, get_mineru_version


def test_get_mineru_version_string():
    version = get_mineru_version()
    assert isinstance(version, str)


def test_parse_pdf_missing_file():
    adapter = MinerUAdapter(MinerUConfig())
    with pytest.raises(FileNotFoundError):
        adapter.parse_pdf(Path("/nonexistent/file.pdf"), Path("/tmp/out"))
