"""Build cell_data for one MinerU table."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional, TYPE_CHECKING

from loguru import logger

from table_recognition_mineru.divider_grid import (
    build_grid,
    split_single_column_into_label_and_amount,
    validate_grid,
)
from table_recognition_mineru.mineru_native_geometry import (
    build_cell_data_from_native_geometry,
    snap_columns_only,
)
from table_recognition_mineru.table_coords import mineru_bbox_to_page_pct
from table_recognition_mineru.table_converter import ConvertedTable

if TYPE_CHECKING:
    from pycognaize.document import Page


def build_cell_data(
    converted: ConvertedTable,
    *,
    page: Optional["Page"],
    native_geometry: Optional[dict],
    ocr_words_pct: Optional[list],
) -> tuple[Dict[str, dict], dict[str, Any]]:
    """
    Derive cell_data from an OCR-anchored divider grid, with native geometry as fallback.

    Columns come from the right-aligned amount clusters (native MinerU X clusters as
    backup) and rows from OCR text lines aligned to the HTML rows, so every line is placed
    in whitespace rather than inherited from MinerU's jittery per-cell boxes. Where page
    OCR is missing or the resulting grid fails its structural checks, the column-snapped
    native geometry is used instead.
    """
    table_pct = mineru_bbox_to_page_pct(converted.source.bbox_norm)
    meta: dict[str, Any] = {
        "table_bbox_norm": converted.source.bbox_norm,
        "table_pct": table_pct,
    }

    if native_geometry is None:
        logger.warning("[GEOM] no native geometry captured — table skipped")
        return {}, meta

    native_cells = build_cell_data_from_native_geometry(
        converted, deepcopy(native_geometry)
    )
    meta["geometry_source_selected"] = native_geometry.get("geometry_source_selected")
    meta["geometry_source_reason"] = native_geometry.get("geometry_source_reason")

    def native_fallback(reason: str) -> tuple[Dict[str, dict], dict[str, Any]]:
        meta["grid_selected"] = "native_columns_snapped"
        meta["grid_fallback_reason"] = reason
        logger.warning("[GEOM] divider grid unavailable ({}) — using native geometry", reason)
        return snap_columns_only(deepcopy(native_cells)), meta

    if page is None or not ocr_words_pct:
        return native_fallback("no page OCR available")

    grid = build_grid(converted, native_cells, ocr_words_pct, table_pct)
    validation = validate_grid(grid.cell_data)
    meta["grid_diagnostics"] = grid.diagnostics
    meta["grid_validation"] = validation

    if not validation.get("valid"):
        return native_fallback(validation.get("reason", "grid validation failed"))

    meta["grid_selected"] = "divider_grid"
    if converted.num_cols == 1:
        meta["single_column_split"] = True
        return (
            split_single_column_into_label_and_amount(grid.cell_data, ocr_words_pct, table_pct),
            meta,
        )
    return grid.cell_data, meta
