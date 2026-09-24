"""Capture MinerU SLANet-plus cell geometry during do_parse (pipeline memory hook)."""

from __future__ import annotations

from typing import Any

import numpy as np

CAPTURED_TABLE_GEOMETRY: list[dict[str, Any]] = []
_PATCHED = False
_ORIG_BATCH_PREDICT = None


def clear_captured_geometry() -> None:
    CAPTURED_TABLE_GEOMETRY.clear()


def get_captured_geometry() -> list[dict[str, Any]]:
    return list(CAPTURED_TABLE_GEOMETRY)


def install_native_geometry_capture() -> None:
    """Hook wireless table batch_predict to retain cell_bboxes/logic_points."""
    global _PATCHED, _ORIG_BATCH_PREDICT

    clear_captured_geometry()
    if _PATCHED:
        return

    from mineru.model.table.rec.slanet_plus.main import PaddleTableModel

    _ORIG_BATCH_PREDICT = PaddleTableModel.batch_predict

    def capturing_batch_predict(self, table_res_list, batch_size=4):
        _ORIG_BATCH_PREDICT(self, table_res_list, batch_size=batch_size)
        for table_res_dict in table_res_list:
            cell_bboxes = table_res_dict.get("wireless_cell_bboxes")
            if cell_bboxes is None:
                continue
            logic_points = table_res_dict.get("wireless_logic_points")
            table_img = table_res_dict.get("table_img")
            if table_img is not None:
                crop_h, crop_w = int(np.asarray(table_img).shape[0]), int(np.asarray(table_img).shape[1])
            else:
                crop_w, crop_h = 1, 1
            wireless_bboxes = np.asarray(cell_bboxes).tolist()
            wireless_logic = (
                np.asarray(logic_points).tolist() if logic_points is not None else []
            )
            CAPTURED_TABLE_GEOMETRY.append(
                {
                    "table_page_bbox_px": table_res_dict.get("table_page_bbox"),
                    "cell_bboxes": wireless_bboxes,
                    "logic_points": wireless_logic,
                    "wireless_cell_bboxes": wireless_bboxes,
                    "wireless_logic_points": wireless_logic,
                    "wired_cell_bboxes": table_res_dict.get("wired_cell_bboxes"),
                    "wired_logic_points": table_res_dict.get("wired_logic_points"),
                    "crop_width": crop_w,
                    "crop_height": crop_h,
                    "geometry_source_selected": "wireless",
                    "geometry_source_reason": (
                        "SLANet-plus wireless_cell_bboxes from PaddleTableModel.batch_predict"
                    ),
                }
            )

    PaddleTableModel.batch_predict = capturing_batch_predict  # type: ignore[method-assign]
    _PATCHED = True


def uninstall_native_geometry_capture() -> None:
    """Restore original MinerU batch_predict if we patched it."""
    global _PATCHED, _ORIG_BATCH_PREDICT
    if not _PATCHED or _ORIG_BATCH_PREDICT is None:
        return
    from mineru.model.table.rec.slanet_plus.main import PaddleTableModel

    PaddleTableModel.batch_predict = _ORIG_BATCH_PREDICT  # type: ignore[method-assign]
    _PATCHED = False
    _ORIG_BATCH_PREDICT = None
