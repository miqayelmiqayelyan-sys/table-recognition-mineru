"""Discover table blocks from MinerU structured output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from table_recognition_mineru.mineru_adapter import MinerUParseResult


@dataclass
class MinerUTableBlock:
    """One table element extracted from MinerU output."""

    index: int
    page_idx: int
    bbox_norm: list[float]
    table_body_html: str
    table_caption: list[str] = field(default_factory=list)
    table_footnote: list[str] = field(default_factory=list)
    img_path: Optional[str] = None
    source: str = "content_list"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def page_number(self) -> int:
        return self.page_idx + 1


def extract_tables_from_parse_result(result: MinerUParseResult) -> list[MinerUTableBlock]:
    """Return all table blocks from content_list.json (primary) and middle.json (fallback)."""
    content_list = result.load_content_list()
    tables = _extract_from_content_list(content_list)
    if tables:
        middle = result.load_middle_json()
        return [_refine_table_bbox(block, content_list, middle) for block in tables]
    return _extract_from_middle_json(result.load_middle_json())


def _extract_from_content_list(content_list: list[dict[str, Any]]) -> list[MinerUTableBlock]:
    blocks: list[MinerUTableBlock] = []
    table_index = 0
    for item in content_list:
        if item.get("type") != "table":
            continue
        html = item.get("table_body") or item.get("html") or ""
        if not html.strip():
            continue
        bbox = item.get("bbox") or [0, 0, 1000, 1000]
        blocks.append(
            MinerUTableBlock(
                index=table_index,
                page_idx=int(item.get("page_idx", 0)),
                bbox_norm=[float(v) for v in bbox],
                table_body_html=html,
                table_caption=list(item.get("table_caption") or []),
                table_footnote=list(item.get("table_footnote") or []),
                img_path=item.get("img_path"),
                source="content_list",
                raw=item,
            )
        )
        table_index += 1
    return blocks


def _extract_from_middle_json(middle: dict[str, Any]) -> list[MinerUTableBlock]:
    blocks: list[MinerUTableBlock] = []
    table_index = 0
    for page in middle.get("pdf_info") or []:
        page_idx = int(page.get("page_idx", 0))
        page_size = page.get("page_size") or [612.0, 792.0]
        for table_block in page.get("tables") or []:
            html = _html_from_middle_table_block(table_block)
            if not html:
                continue
            bbox_pts = table_block.get("bbox") or [0, 0, page_size[0], page_size[1]]
            bbox_norm = _points_bbox_to_norm(bbox_pts, page_size)
            blocks.append(
                MinerUTableBlock(
                    index=table_index,
                    page_idx=page_idx,
                    bbox_norm=bbox_norm,
                    table_body_html=html,
                    source="middle_json",
                    raw=table_block,
                )
            )
            table_index += 1
    return blocks


def _html_from_middle_table_block(table_block: dict[str, Any]) -> str:
    for sub in table_block.get("blocks") or []:
        if sub.get("type") != "table_body":
            continue
        for line in sub.get("lines") or []:
            for span in line.get("spans") or []:
                content = span.get("content")
                if isinstance(content, str) and "<table" in content.lower():
                    return content
    return ""


def _page_layout_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all top-level layout blocks MinerU may store on a page."""
    blocks: list[dict[str, Any]] = []
    for key in ("tables", "preproc_blocks", "para_blocks"):
        blocks.extend(page.get(key) or [])
    return blocks


def _iter_table_caption_norm_bboxes(
    page: dict[str, Any],
) -> list[list[float]]:
    """Collect table_caption bboxes from middle.json (0–1000 normalized coords)."""
    page_w, page_h = page.get("page_size") or [612.0, 792.0]
    captions: list[list[float]] = []

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") == "table_caption":
            cb = node.get("bbox") or []
            if len(cb) == 4:
                captions.append(_points_bbox_to_norm([float(v) for v in cb], [page_w, page_h]))
        for child in node.get("blocks") or []:
            if isinstance(child, dict):
                walk(child)

    for block in _page_layout_blocks(page):
        walk(block)
    return captions


def _push_top_below_overlapping_bbox(
    table_bbox: list[float],
    overlap_bbox: list[float],
) -> float:
    """Raise table top to sit below a horizontally overlapping region."""
    x0, y0, x1, y1 = table_bbox
    ox0, oy0, ox1, oy1 = overlap_bbox
    if ox1 <= x0 or ox0 >= x1:
        return y0
    if oy1 <= y0:
        return y0
    if oy0 < y1:
        return max(y0, oy1)
    return y0


def _refine_table_bbox(
    block: MinerUTableBlock,
    content_list: list[dict[str, Any]],
    middle: Optional[dict[str, Any]] = None,
) -> MinerUTableBlock:
    """Push table top below overlapping MinerU title/text/caption blocks on the same page."""
    x0, y0, x1, y1 = block.bbox_norm
    for item in content_list:
        if item.get("type") != "text":
            continue
        if int(item.get("page_idx", 0)) != block.page_idx:
            continue
        text_bbox = item.get("bbox") or []
        if len(text_bbox) != 4:
            continue
        y0 = _push_top_below_overlapping_bbox(
            [x0, y0, x1, y1],
            [float(v) for v in text_bbox],
        )

    for page in (middle or {}).get("pdf_info") or []:
        if int(page.get("page_idx", 0)) != block.page_idx:
            continue
        for caption_norm in _iter_table_caption_norm_bboxes(page):
            y0 = _push_top_below_overlapping_bbox([x0, y0, x1, y1], caption_norm)

    if y0 != block.bbox_norm[1]:
        block.bbox_norm = [x0, y0, x1, y1]
    return block


def _points_bbox_to_norm(bbox: list[float], page_size: list[float]) -> list[float]:
    width = float(page_size[0]) or 1.0
    height = float(page_size[1]) or 1.0
    x0, y0, x1, y1 = bbox
    return [
        x0 / width * 1000.0,
        y0 / height * 1000.0,
        x1 / width * 1000.0,
        y1 / height * 1000.0,
    ]
