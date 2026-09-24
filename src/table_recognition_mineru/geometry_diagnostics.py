"""Verify a finished grid against page OCR (measurement only — never moves geometry)."""

from __future__ import annotations

from typing import Any, Dict, Sequence

# OCR reports boxes padded well beyond the glyphs — on some scans a box is nearly as tall
# as the whole row pitch — so a line drawn in the visible gap still lands inside a box.
# Shrinking to this fraction of the box gives the band where the ink actually is.
INK_INSET_FRACTION = 0.15
# Outside the ink but this close to the padded box: the line is tight against the text.
DEFAULT_CLEARANCE_PCT = 0.02


def _boxes(word: dict) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """Return the word's reported box and its inner ink band."""
    left, top = float(word["left"]), float(word["top"])
    right, bottom = float(word["right"]), float(word["bottom"])
    pad_y = (bottom - top) * INK_INSET_FRACTION
    # Padding is roughly even on all sides, but a narrow box like "%" must not collapse.
    pad_x = min(pad_y, (right - left) * 0.4)
    return (
        (left, top, right, bottom),
        (left + pad_x, top + pad_y, right - pad_x, bottom - pad_y),
    )


def verify_grid_against_page_ocr(
    cell_data: Dict[str, dict],
    page_words_pct: Sequence[dict],
    clearance: float = DEFAULT_CLEARANCE_PCT,
) -> dict[str, Any]:
    """Check what each cell edge hits along the span it is drawn over.

    Edges through the ink are reported as cuts; edges that clear the ink but sit against
    the reported box are reported separately as grazes, because those are usually OCR
    padding rather than a line the reader would see touching the text.
    """
    h_edges: Dict[float, list[tuple[float, float]]] = {}
    v_edges: Dict[float, list[tuple[float, float]]] = {}
    for cell in cell_data.values():
        left = float(cell["left"])
        top = float(cell["top"])
        right = left + float(cell["width"])
        bottom = top + float(cell["height"])
        for y in (top, bottom):
            h_edges.setdefault(round(y, 4), []).append((left, right))
        for x in (left, right):
            v_edges.setdefault(round(x, 4), []).append((top, bottom))

    def _scan(
        edges: Dict[float, list[tuple[float, float]]], horizontal: bool
    ) -> tuple[list[dict], list[dict]]:
        cuts: list[dict] = []
        grazes: list[dict] = []
        for position, spans in sorted(edges.items()):
            cut_texts: list[str] = []
            graze_texts: list[str] = []
            for word in page_words_pct:
                box, ink = _boxes(word)
                if horizontal:
                    along = any(box[2] > s0 and box[0] < s1 for s0, s1 in spans)
                    through_ink = ink[1] <= position <= ink[3]
                    touching = box[1] - clearance <= position <= box[3] + clearance
                else:
                    along = any(box[3] > s0 and box[1] < s1 for s0, s1 in spans)
                    through_ink = ink[0] <= position <= ink[2]
                    touching = box[0] - clearance <= position <= box[2] + clearance
                if not along:
                    continue
                if through_ink:
                    cut_texts.append(str(word.get("ocr_text", "")))
                elif touching:
                    graze_texts.append(str(word.get("ocr_text", "")))
            if cut_texts:
                cuts.append({"position": position, "words": sorted(set(cut_texts))})
            elif graze_texts:
                grazes.append({"position": position, "words": sorted(set(graze_texts))})
        return cuts, grazes

    h_cuts, h_grazes = _scan(h_edges, horizontal=True)
    v_cuts, v_grazes = _scan(v_edges, horizontal=False)
    return {
        "horizontal_edges": len(h_edges),
        "vertical_edges": len(v_edges),
        "horizontal_cuts": h_cuts,
        "vertical_cuts": v_cuts,
        "horizontal_grazes": h_grazes,
        "vertical_grazes": v_grazes,
        "clean": not h_cuts and not v_cuts,
    }
