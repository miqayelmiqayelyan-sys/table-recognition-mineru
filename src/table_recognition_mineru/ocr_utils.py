"""Page OCR helpers for MinerU table regions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from pycognaize.document import Page


def page_dimensions_px(page: "Page") -> tuple[int, int]:
    """Page size in the pixel space used for tag percentages.

    ``page.image_arr`` is the rendered bitmap and may differ from the recorded page
    dimensions; pycognaize converts tags with ``image_width``/``image_height``, so every
    percentage we emit must use those or the whole grid drifts proportionally to y.
    """
    return int(page.image_width), int(page.image_height)


def extract_table_ocr_words_pct(page: "Page", table_pct: Dict[str, float]) -> List[dict]:
    """Return OCR words inside a table bbox, converted to page percentages."""
    img_w, img_h = page_dimensions_px(page)
    left_px = table_pct["left"] / 100.0 * img_w
    right_px = table_pct["right"] / 100.0 * img_w
    top_px = table_pct["top"] / 100.0 * img_h
    bottom_px = table_pct["bottom"] / 100.0 * img_h

    raw = page.extract_area_words(
        left=left_px,
        right=right_px,
        top=top_px,
        bottom=bottom_px,
        threshold=0.3,
    ) or []

    min_top_pct = table_pct["top"]
    words: list[dict] = []
    for word in raw:
        top_pct = float(word["top"]) / img_h * 100.0
        bottom_pct = float(word["bottom"]) / img_h * 100.0
        if bottom_pct <= min_top_pct:
            continue
        words.append(
            {
                "ocr_text": word.get("ocr_text", ""),
                "left": float(word["left"]) / img_w * 100.0,
                "top": top_pct,
                "right": float(word["right"]) / img_w * 100.0,
                "bottom": bottom_pct,
            }
        )
    return words


def extract_page_ocr_words_pct(page: "Page") -> List[dict]:
    """Return every OCR word on the page in page percentages.

    ``extract_table_ocr_words_pct`` drops words that are mostly outside the MinerU bbox,
    so it cannot be used to prove a grid is clean — a divider may miss every word it
    knows about while still cutting one the viewer renders. Verification uses this instead.
    """
    img_w, img_h = page_dimensions_px(page)
    words: list[dict] = []
    for word in page.get_ocr_formatted()["words"]:
        text = str(word.get("ocr_text", ""))
        if not text.strip():
            continue
        words.append(
            {
                "ocr_text": text,
                "left": float(word["left"]) / img_w * 100.0,
                "top": float(word["top"]) / img_h * 100.0,
                "right": float(word["right"]) / img_w * 100.0,
                "bottom": float(word["bottom"]) / img_h * 100.0,
            }
        )
    return words
