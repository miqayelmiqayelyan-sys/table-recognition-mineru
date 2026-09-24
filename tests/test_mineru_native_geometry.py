from copy import deepcopy

from table_recognition_mineru.mineru_native_geometry import (
    build_cell_data_from_native_geometry,
    cell_bbox_to_crop_rect,
    snap_columns_only,
)
from table_recognition_mineru.table_converter import ConvertedCell, ConvertedTable
from table_recognition_mineru.table_extractor import MinerUTableBlock


def _two_by_two() -> tuple[ConvertedTable, dict]:
    block = MinerUTableBlock(
        index=0,
        page_idx=0,
        bbox_norm=[0, 0, 1000, 1000],
        table_body_html="<table></table>",
    )
    converted = ConvertedTable(
        source=block,
        num_rows=2,
        num_cols=2,
        cells=[
            ConvertedCell(row=0, col=0, value="A"),
            ConvertedCell(row=0, col=1, value="B"),
            ConvertedCell(row=1, col=0, value="C"),
            ConvertedCell(row=1, col=1, value="D"),
        ],
    )
    geometry = {
        "crop_width": 200,
        "crop_height": 100,
        "cell_bboxes": [
            [0, 0, 100, 0, 100, 40, 0, 40],
            [100, 0, 200, 0, 200, 40, 100, 40],
            [0, 45, 100, 45, 100, 95, 0, 95],
            [100, 50, 200, 50, 200, 100, 100, 100],
        ],
    }
    return converted, geometry


def test_cell_bbox_quad_to_rect():
    rect = cell_bbox_to_crop_rect([0, 0, 100, 0, 100, 50, 0, 50])
    assert rect == (0.0, 0.0, 100.0, 50.0)


def test_native_geometry_keeps_raw_per_cell_positions():
    """No smoothing here — the divider grid needs MinerU's positions as measured."""
    converted, geometry = _two_by_two()

    cell_data = build_cell_data_from_native_geometry(converted, geometry)

    assert len(cell_data) == 4
    # Rows 1 and 2 of the same column start where their own bboxes start (45 and 50 of 100).
    assert cell_data["1:2"]["top"] != cell_data["2:2"]["top"]
    assert cell_data["1:1"]["top"] == 0.0


def test_native_geometry_records_source():
    converted, geometry = _two_by_two()

    build_cell_data_from_native_geometry(converted, geometry)

    assert geometry["geometry_source_selected"] == "wireless"
    assert geometry["geometry_source_reason"]


def test_native_mapping_skipped_when_html_was_merged():
    """After marker-column merge the HTML list is shorter; pairing by index would be wrong."""
    converted, geometry = _two_by_two()
    converted.cells = converted.cells[:2]

    assert build_cell_data_from_native_geometry(converted, geometry) == {}


def test_snap_columns_only_preserves_y_and_unifies_column_x():
    cell_data = {
        "1:1": {"left": 1.0, "top": 10.0, "width": 40.1, "height": 2.0, "colspan": 1, "rowspan": 1, "value": "a"},
        "2:1": {"left": 50.2, "top": 10.0, "width": 39.8, "height": 2.0, "colspan": 1, "rowspan": 1, "value": "b"},
        "1:2": {"left": 1.3, "top": 15.5, "width": 39.5, "height": 3.0, "colspan": 1, "rowspan": 1, "value": "c"},
        "2:2": {"left": 49.9, "top": 16.0, "width": 40.5, "height": 2.5, "colspan": 1, "rowspan": 1, "value": "d"},
    }
    before = deepcopy(cell_data)
    snapped = snap_columns_only(deepcopy(cell_data))
    unique_lefts_before = len({round(c["left"], 3) for c in before.values()})
    unique_lefts_after = len({round(c["left"], 3) for c in snapped.values()})
    assert unique_lefts_before > unique_lefts_after
    for key in before:
        assert snapped[key]["top"] == before[key]["top"]
        assert snapped[key]["height"] == before[key]["height"]
    assert snapped["1:1"]["left"] == snapped["1:2"]["left"]
    assert snapped["2:1"]["left"] == snapped["2:2"]["left"]
