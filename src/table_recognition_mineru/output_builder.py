"""Convert MinerU tables into pycognaize TableField objects."""

from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from table_recognition_mineru.table_converter import ConvertedTable
from table_recognition_mineru.table_coords import mineru_bbox_to_page_pct

if TYPE_CHECKING:
    from pycognaize.document import Page
    from pycognaize.document.field import TableField


def sanitize_cell_data_for_table_tag(cell_data: Dict[str, dict]) -> Dict[str, dict]:
    """
    Clamp spans so pycognaize TableTag can build its dataframe.

    TableTag numbers columns by sorted unique ``left`` values and rows by unique ``top``
    values, then walks ``range(index, index + span)`` into a frame of exactly that size.
    A span must therefore fit in the positions remaining *from the cell's own index*, not
    merely in the table: a cell in the last column with ``colspan=2`` raises IndexError.
    Native geometry carries MinerU's HTML spans, which is where oversized ones come from.
    """
    if not cell_data:
        return cell_data

    lefts = sorted({float(cell["left"]) for cell in cell_data.values()})
    tops = sorted({float(cell["top"]) for cell in cell_data.values()})

    for cell in cell_data.values():
        cols_left = len(lefts) - lefts.index(float(cell["left"]))
        rows_left = len(tops) - tops.index(float(cell["top"]))
        cell["colspan"] = max(1, min(int(cell.get("colspan", 1)), cols_left))
        cell["rowspan"] = max(1, min(int(cell.get("rowspan", 1)), rows_left))

    return cell_data


def table_pct_from_cell_data(
    cell_data: Dict[str, dict],
    fallback: Dict[str, float],
) -> Dict[str, float]:
    """Fit outer table tag to actual cell grid (excludes title area above first row)."""
    if not cell_data:
        return fallback
    left = min(cell["left"] for cell in cell_data.values())
    top = min(cell["top"] for cell in cell_data.values())
    right = max(cell["left"] + cell["width"] for cell in cell_data.values())
    bottom = max(cell["top"] + cell["height"] for cell in cell_data.values())
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def build_table_field(
    table_pct: Dict[str, float],
    cell_data: Dict[str, dict],
    page: "Page",
    confidence: float = 1.0,
) -> "TableField":
    """Create a pycognaize TableField (external contract only)."""
    from pycognaize.document.field import TableField
    from pycognaize.document.tag import TableTag

    table_tag = TableTag(
        left=table_pct["left"],
        right=table_pct["right"],
        top=table_pct["top"],
        bottom=table_pct["bottom"],
        page=page,
        cell_data=cell_data,
    )
    return TableField(name="Table", tag=table_tag, confidence=float(confidence))


def converted_table_to_table_field(
    converted: ConvertedTable,
    page_lookup: dict[int, "Page"],
    *,
    ocr_words: Optional[list] = None,
    native_geometry: Optional[dict] = None,
    geometry_meta_out: Optional[list] = None,
) -> Optional["TableField"]:
    """Build one TableField for a converted MinerU table."""
    page_number = converted.source.page_number
    page = page_lookup.get(page_number)
    if page is None:
        return None

    from table_recognition_mineru.geometry_builder import build_cell_data

    fallback_table_pct = mineru_bbox_to_page_pct(converted.source.bbox_norm)

    cell_data, geom_meta = build_cell_data(
        converted,
        page=page,
        native_geometry=native_geometry,
        ocr_words_pct=ocr_words,
    )
    if geometry_meta_out is not None:
        geometry_meta_out.append(geom_meta)

    if not cell_data:
        return None

    cell_data = sanitize_cell_data_for_table_tag(cell_data)
    table_pct = table_pct_from_cell_data(cell_data, fallback_table_pct)
    return build_table_field(table_pct, cell_data, page)
