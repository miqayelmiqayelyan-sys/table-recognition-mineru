"""Integration test: fixture MinerU JSON → converted tables (no GPU)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from table_recognition_mineru.mineru_adapter import MinerUParseResult
from table_recognition_mineru.table_converter import convert_mineru_table
from table_recognition_mineru.table_extractor import extract_tables_from_parse_result

FIXTURE = Path(__file__).parent / "fixtures" / "sample_content_list.json"


@pytest.fixture
def sample_content_list() -> list[dict]:
    if not FIXTURE.is_file():
        pytest.skip("fixture not present")
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_integration_fixture_tables(sample_content_list):
    result = MinerUParseResult(
        pdf_stem="sample_balance_sheet",
        output_dir=Path("."),
        mineru_version="fixture",
        backend="pipeline",
    )

    class FixtureResult(MinerUParseResult):
        def load_content_list(self):
            return sample_content_list

    blocks = extract_tables_from_parse_result(FixtureResult(
        pdf_stem=result.pdf_stem,
        output_dir=result.output_dir,
        mineru_version=result.mineru_version,
        backend=result.backend,
    ))
    assert len(blocks) >= 1
    converted = convert_mineru_table(blocks[0])
    assert converted.num_rows >= 2
    assert converted.num_cols >= 2
    values = {c.value for c in converted.cells}
    assert any("Assets" in v or "Cash" in v for v in values)
