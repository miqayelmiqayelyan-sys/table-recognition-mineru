from table_recognition_mineru.output_builder import (
    mineru_bbox_to_page_pct,
    sanitize_cell_data_for_table_tag,
)
from table_recognition_mineru.table_converter import ConvertedCell, ConvertedTable
from table_recognition_mineru.table_extractor import MinerUTableBlock


def test_mineru_bbox_to_page_pct():
    pct = mineru_bbox_to_page_pct([100, 200, 900, 800])
    assert pct["left"] == 10.0
    assert pct["top"] == 20.0
    assert pct["right"] == 90.0
    assert pct["bottom"] == 80.0


def test_sanitize_clamps_span_reaching_past_the_last_column():
    """TableTag walks range(index, index + span) into a fixed frame, so it must fit."""
    cell_data = {
        "1:1": {"colspan": 1, "rowspan": 1, "left": 5.0, "top": 10.0, "width": 40.0, "height": 2.0, "value": "a"},
        # Last column, but MinerU's HTML claims it spans two: index 1 + 2 > 2 columns.
        "2:1": {"colspan": 2, "rowspan": 1, "left": 45.0, "top": 10.0, "width": 40.0, "height": 2.0, "value": "b"},
        "1:2": {"colspan": 1, "rowspan": 3, "left": 5.0, "top": 12.0, "width": 40.0, "height": 2.0, "value": "c"},
    }

    sanitize_cell_data_for_table_tag(cell_data)

    assert cell_data["2:1"]["colspan"] == 1
    assert cell_data["1:2"]["rowspan"] == 1
    assert cell_data["1:1"]["colspan"] == 1


def test_sanitize_keeps_a_span_that_fits():
    cell_data = {
        "1:1": {"colspan": 2, "rowspan": 1, "left": 5.0, "top": 10.0, "width": 40.0, "height": 2.0, "value": "a"},
        "2:1": {"colspan": 1, "rowspan": 1, "left": 45.0, "top": 10.0, "width": 40.0, "height": 2.0, "value": "b"},
    }

    sanitize_cell_data_for_table_tag(cell_data)

    assert cell_data["1:1"]["colspan"] == 2


def test_sanitize_cell_data_clamps_colspan_for_single_column_geometry():
    cell_data = {
        "1:1": {
            "colspan": 2,
            "rowspan": 1,
            "left": 5.0,
            "top": 10.0,
            "width": 90.0,
            "height": 2.0,
            "value": "Total",
        },
        "1:2": {
            "colspan": 1,
            "rowspan": 1,
            "left": 5.0,
            "top": 12.0,
            "width": 90.0,
            "height": 2.0,
            "value": "Row",
        },
    }
    sanitize_cell_data_for_table_tag(cell_data)
    assert cell_data["1:1"]["colspan"] == 1
