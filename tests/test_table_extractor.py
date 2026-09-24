from table_recognition_mineru.mineru_adapter import MinerUParseResult
from table_recognition_mineru.table_extractor import extract_tables_from_parse_result


def test_extract_tables_from_content_list():
    class FakeResult(MinerUParseResult):
        def load_content_list(self):
            return [
                {"type": "text", "text": "hello", "page_idx": 0, "bbox": [0, 0, 100, 100]},
                {
                    "type": "table",
                    "page_idx": 1,
                    "bbox": [62, 480, 946, 904],
                    "table_body": "<html><body><table><tr><td>A</td><td>1</td></tr></table></body></html>",
                    "table_caption": ["Table 1"],
                },
            ]

    blocks = extract_tables_from_parse_result(FakeResult(
        pdf_stem="demo",
        output_dir=__import__("pathlib").Path("."),
        mineru_version="test",
        backend="pipeline",
    ))
    assert len(blocks) == 1
    assert blocks[0].page_number == 2
    assert "A" in blocks[0].table_body_html


def test_extract_tables_empty():
    class Empty(MinerUParseResult):
        def load_content_list(self):
            return []

        def load_middle_json(self):
            return {}

    assert extract_tables_from_parse_result(Empty(
        pdf_stem="x",
        output_dir=__import__("pathlib").Path("."),
        mineru_version="test",
        backend="pipeline",
    )) == []
