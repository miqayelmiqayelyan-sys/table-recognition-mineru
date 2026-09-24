"""Shared MinerU bbox → page percentage helpers."""

from __future__ import annotations

from typing import Dict


def mineru_bbox_to_page_pct(bbox_norm: list[float]) -> Dict[str, float]:
    """Map MinerU 0–1000 bbox to page percentages."""
    x0, y0, x1, y1 = bbox_norm
    left = x0 / 10.0
    top = y0 / 10.0
    right = x1 / 10.0
    bottom = y1 / 10.0
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }
