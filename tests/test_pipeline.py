from pathlib import Path

from table_recognition_mineru.config import AppConfig
from table_recognition_mineru.document_parser import resolve_pdf_path
from table_recognition_mineru.mineru_adapter import MinerUParseResult
from table_recognition_mineru.pipeline import MinerUPipeline
from table_recognition_mineru.table_converter import convert_mineru_table
from table_recognition_mineru.table_extractor import MinerUTableBlock, extract_tables_from_parse_result


def test_resolve_pdf_path_explicit(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert resolve_pdf_path(pdf_path=pdf) == pdf.resolve()


def test_pipeline_without_pages_builds_converted_tables(monkeypatch, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    html = (
        "<html><body><table>"
        "<tr><td>Assets</td><td>100</td></tr>"
        "<tr><td>Total</td><td>100</td></tr>"
        "</table></body></html>"
    )

    mineru_out = tmp_path / "mineru_out"
    mineru_out.mkdir()
    fake_result = MinerUParseResult(
        pdf_stem="sample",
        output_dir=mineru_out,
        mineru_version="test",
        backend="pipeline",
        content_list_path=mineru_out / "sample_content_list.json",
    )
    fake_result.content_list_path.write_text(
        __import__("json").dumps(
            [
                {
                    "type": "table",
                    "page_idx": 0,
                    "bbox": [50, 100, 950, 900],
                    "table_body": html,
                }
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_yaml()
    config.pipeline.output_dir = str(tmp_path / "out")
    pipeline = MinerUPipeline(config)
    monkeypatch.setattr(pipeline.adapter, "parse_pdf", lambda _p, _o: fake_result)

    result = pipeline.process_pdf(pdf)
    assert len(result.converted_tables) == 1
    assert result.converted_tables[0]["num_rows"] == 2
    assert result.converted_tables[0]["cells"][0]["value"] == "Assets"


def test_merged_cells_in_html():
    block = MinerUTableBlock(
        index=0,
        page_idx=0,
        bbox_norm=[0, 0, 1000, 1000],
        table_body_html=(
            "<html><body><table>"
            '<tr><td rowspan="2">Site</td><td colspan="2">Percentile</td></tr>'
            "<tr><td>10</td><td>20</td></tr>"
            "<tr><td>A</td><td>P</td><td>P</td></tr>"
            "</table></body></html>"
        ),
    )
    converted = convert_mineru_table(block)
    anchor = next(c for c in converted.cells if c.value == "Site")
    assert anchor.rowspan == 2
    assert anchor.colspan == 1
    header = next(c for c in converted.cells if c.value == "Percentile")
    assert header.colspan == 2
