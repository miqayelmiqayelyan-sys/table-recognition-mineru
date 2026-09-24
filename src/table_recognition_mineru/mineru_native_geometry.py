"""Build cell_data from MinerU native SLANet-plus cell bboxes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Optional, Sequence

import numpy as np
from loguru import logger

from table_recognition_mineru.table_coords import mineru_bbox_to_page_pct
from table_recognition_mineru.table_converter import ConvertedTable


def resolve_native_geometry_source(
    geometry: dict[str, Any],
    html_cell_count: int,
) -> tuple[str, list, list, str]:
    """
    Pick wireless vs wired native bboxes.

    Wired bboxes are only present when MinerU pipeline stores them on ``table_res_dict``.
    Default pipeline capture uses wireless SLANet-plus output.
    """
    wireless = geometry.get("wireless_cell_bboxes") or geometry.get("cell_bboxes") or []
    wireless_logic = geometry.get("wireless_logic_points") or geometry.get("logic_points") or []
    wired = geometry.get("wired_cell_bboxes") or []
    wired_logic = geometry.get("wired_logic_points") or []

    def _score(bboxes: list, logic: list) -> tuple[int, int]:
        return (len(bboxes), len(logic))

    w_score = _score(wireless, wireless_logic)
    d_score = _score(wired, wired_logic)

    if d_score[0] >= html_cell_count and d_score[0] > w_score[0]:
        return (
            "wired",
            wired,
            wired_logic,
            "wired_cell_bboxes count >= HTML cells and exceeds wireless count",
        )
    if w_score[0] > 0:
        return (
            "wireless",
            wireless,
            wireless_logic,
            geometry.get(
                "geometry_source_reason",
                "wireless_cell_bboxes from SLANet-plus (default pipeline capture)",
            ),
        )
    if d_score[0] > 0:
        return ("wired", wired, wired_logic, "wireless missing; wired bboxes present")
    return ("none", [], [], "no native cell bboxes captured")


def _cell_key_from_logic(logic_point: Sequence[float], fallback_col: int, fallback_row: int) -> tuple[str, int, int]:
    if logic_point and len(logic_point) >= 4:
        r0, r1, c0, c1 = (int(v) for v in logic_point[:4])
        return f"{c0 + 1}:{r0 + 1}", max(c1 - c0 + 1, 1), max(r1 - r0 + 1, 1)
    return f"{fallback_col + 1}:{fallback_row + 1}", 1, 1


def cell_bbox_to_crop_rect(bbox: Sequence[float] | Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    """Normalize SLANet cell bbox (quad or rect) to axis-aligned crop rect."""
    arr = np.asarray(bbox, dtype=float)
    if arr.ndim == 2 and arr.shape[1] == 2:
        return (
            float(arr[:, 0].min()),
            float(arr[:, 1].min()),
            float(arr[:, 0].max()),
            float(arr[:, 1].max()),
        )
    if arr.size == 8:
        arr = arr.reshape(4, 2)
        return (
            float(arr[:, 0].min()),
            float(arr[:, 1].min()),
            float(arr[:, 0].max()),
            float(arr[:, 1].max()),
        )
    if arr.size == 4:
        x0, y0, x1, y1 = arr.tolist()
        return float(x0), float(y0), float(x1), float(y1)
    raise ValueError(f"Unsupported cell bbox shape: {arr.shape}")


def _crop_rect_to_page_pct(
    rect: tuple[float, float, float, float],
    *,
    crop_w: float,
    crop_h: float,
    table_pct: dict[str, float],
) -> tuple[float, float, float, float]:
    """Map table-crop pixels to page percentages via MinerU bbox fractions.

    Cell bboxes are relative to the table crop. MinerU ``bbox_norm`` uses the same
    page-normalized frame as the tags, so map through ``table_pct`` instead of absolute
    MinerU render pixels (which differ from ``page.image_arr`` dimensions).
    """
    x0, y0, x1, y1 = rect
    x0 = max(0.0, min(float(x0), crop_w))
    x1 = max(0.0, min(float(x1), crop_w))
    y0 = max(0.0, min(float(y0), crop_h))
    y1 = max(0.0, min(float(y1), crop_h))
    if x1 <= x0 or y1 <= y0:
        x1 = min(x0 + 1.0, crop_w)
        y1 = min(y0 + 1.0, crop_h)
    left = table_pct["left"] + (x0 / crop_w) * table_pct["width"]
    top = table_pct["top"] + (y0 / crop_h) * table_pct["height"]
    width = ((x1 - x0) / crop_w) * table_pct["width"]
    height = ((y1 - y0) / crop_h) * table_pct["height"]
    return left, top, width, height


def _robust_low(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    med = float(np.median(values))
    mad = float(np.median([abs(v - med) for v in values]))
    if mad <= 1e-9:
        return float(min(values))
    kept = [v for v in values if abs(v - med) <= 2.5 * mad]
    return float(min(kept if kept else values))


def _robust_high(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    med = float(np.median(values))
    mad = float(np.median([abs(v - med) for v in values]))
    if mad <= 1e-9:
        return float(max(values))
    kept = [v for v in values if abs(v - med) <= 2.5 * mad]
    return float(max(kept if kept else values))


def snap_columns_only(cell_data: Dict[str, dict]) -> Dict[str, dict]:
    """
    Unify column left/width bands from native MinerU jitter.

    Does not modify ``top`` or ``height`` (native row Y preserved).
    """
    if not cell_data:
        return cell_data

    by_col: dict[int, list[dict]] = defaultdict(list)
    for key, cell in cell_data.items():
        by_col[int(key.split(":")[0])].append(cell)

    col_ids = sorted(by_col)
    col_bounds: list[tuple[float, float]] = []
    for col_id in col_ids:
        lefts = [cell["left"] for cell in by_col[col_id]]
        rights = [cell["left"] + cell["width"] for cell in by_col[col_id]]
        col_bounds.append((_robust_low(lefts), _robust_high(rights)))

    for idx in range(1, len(col_bounds)):
        prev_left, prev_right = col_bounds[idx - 1]
        cur_left, cur_right = col_bounds[idx]
        if cur_left < prev_right:
            divider = (prev_right + cur_left) / 2.0
            col_bounds[idx - 1] = (prev_left, divider)
            col_bounds[idx] = (divider, max(cur_right, divider + 0.05))

    for col_id, (left, right) in zip(col_ids, col_bounds):
        width = max(right - left, 0.05)
        for cell in by_col[col_id]:
            cell["left"] = left
            cell["width"] = width

    logger.debug(
        "[MINERU-GEO] snap_columns_only — {} column(s), unique lefts {}",
        len(col_ids),
        len({round(by_col[c][0]["left"], 4) for c in col_ids}),
    )
    return cell_data


def build_cell_data_from_native_geometry(
    converted: ConvertedTable,
    geometry: dict[str, Any],
) -> Dict[str, dict]:
    """Map MinerU cell bboxes (table-crop pixels) into raw page percentages.

    No smoothing is applied here — the divider grid is built from these positions, and
    ``snap_columns_only`` handles the column jitter for the fallback.
    """
    if not converted.cells:
        return {}

    source, cell_bboxes, logic_points, source_reason = resolve_native_geometry_source(
        geometry,
        html_cell_count=len(converted.cells),
    )
    if not cell_bboxes:
        logger.warning("[MINERU-GEO] no native cell bboxes — {}", source_reason)
        return {}

    crop_w = max(float(geometry.get("crop_width") or 1), 1.0)
    crop_h = max(float(geometry.get("crop_height") or 1), 1.0)
    table_pct = mineru_bbox_to_page_pct(converted.source.bbox_norm)

    if len(cell_bboxes) != len(converted.cells):
        # Marker-column merge changes the HTML cell list; pairing by index would
        # attach the wrong bbox to the wrong value, so native geometry sits out.
        logger.warning(
            "[MINERU-GEO] {} bbox count {} != HTML cell count {} — skipping native mapping",
            source,
            len(cell_bboxes),
            len(converted.cells),
        )
        geometry["geometry_source_selected"] = source
        geometry["geometry_source_reason"] = source_reason
        return {}

    cell_data: Dict[str, dict] = {}
    for i, cell in enumerate(converted.cells):
        if i >= len(cell_bboxes):
            break
        try:
            rect = cell_bbox_to_crop_rect(cell_bboxes[i])
        except ValueError:
            continue
        x0, y0, x1, y1 = rect
        if x1 <= x0 or y1 <= y0:
            continue

        left, top, width, height = _crop_rect_to_page_pct(
            rect,
            crop_w=crop_w,
            crop_h=crop_h,
            table_pct=table_pct,
        )

        lp = logic_points[i] if i < len(logic_points) else None
        if lp is not None:
            key, _, _ = _cell_key_from_logic(lp, cell.col, cell.row)
        else:
            key = f"{cell.col + 1}:{cell.row + 1}"
        cell_data[key] = {
            "colspan": cell.colspan,
            "rowspan": cell.rowspan,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "value": cell.value,
        }

    logger.debug(
        "[MINERU-GEO] {} — {} cell(s) crop {}x{}",
        source,
        len(cell_data),
        int(crop_w),
        int(crop_h),
    )
    geometry["geometry_source_selected"] = source
    geometry["geometry_source_reason"] = source_reason
    return cell_data
