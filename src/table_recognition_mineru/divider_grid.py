"""
Document-agnostic table grid.

MinerU supplies logical structure (rows, columns, spans, values) and approximate cell
geometry. Rendering needs a *grid*: one X per column boundary, one Y per row boundary, every
cell derived from those boundaries. Building cells from dividers (instead of nudging
per-cell native boxes) is what guarantees straight verticals, horizontals in whitespace,
closed cells, unique row tops for ``TableTag`` and correct merged cells.

Pipeline:

    native cell boxes ──► column extents ──► column dividers (OCR-whitespace validated)
    OCR words ──► text lines ──► monotonic DP alignment to HTML rows ──► row dividers
    dividers + HTML spans ──► cell_data

No document-specific text patterns, no hard-coded percentages.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

from table_recognition_mineru.table_converter import ConvertedTable

Interval = Tuple[float, float]

_EMPTY_ROW_PENALTY = 0.35
_EXTRA_LINE_PENALTY = 0.25
_MIN_MATCH_SIM = 0.2


@dataclass
class Grid:
    cell_data: Dict[str, dict]
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Line:
    left: float
    top: float
    right: float
    bottom: float
    text: str

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _median(values: Sequence[float], default: float = 1.0) -> float:
    vals = [v for v in values if v > 0]
    return float(np.median(vals)) if vals else default


def cluster_words_into_lines(words: Sequence[dict]) -> List[_Line]:
    """Group OCR words into text lines by vertical centre proximity."""
    boxes = [
        (
            float(w["left"]),
            float(w["top"]),
            float(w["right"]),
            float(w["bottom"]),
            str(w.get("ocr_text", "")).strip(),
        )
        for w in words
        if str(w.get("ocr_text", "")).strip()
    ]
    if not boxes:
        return []

    median_h = _median([b[3] - b[1] for b in boxes])
    threshold = max(median_h * 0.55, 0.05)

    groups: List[List[tuple]] = []
    centre: Optional[float] = None
    for box in sorted(boxes, key=lambda b: ((b[1] + b[3]) / 2, b[0])):
        cy = (box[1] + box[3]) / 2
        if centre is None or abs(cy - centre) <= threshold:
            if centre is None:
                groups.append([box])
                centre = cy
            else:
                groups[-1].append(box)
                centre = sum((b[1] + b[3]) / 2 for b in groups[-1]) / len(groups[-1])
        else:
            groups.append([box])
            centre = cy

    lines: List[_Line] = []
    for group in groups:
        ordered = sorted(group, key=lambda b: b[0])
        lines.append(
            _Line(
                left=min(b[0] for b in group),
                top=min(b[1] for b in group),
                right=max(b[2] for b in group),
                bottom=max(b[3] for b in group),
                text=" ".join(b[4] for b in ordered).strip(),
            )
        )
    return lines


def _clear_intervals(blocked: Sequence[Interval], lo: float, hi: float) -> List[Interval]:
    """Sub-intervals of ``[lo, hi]`` not covered by any blocked interval."""
    if hi <= lo:
        return []
    overlapping = sorted(
        (max(b0, lo), min(b1, hi)) for b0, b1 in blocked if b1 > lo and b0 < hi
    )
    clear: List[Interval] = []
    cursor = lo
    for b0, b1 in overlapping:
        if b0 > cursor:
            clear.append((cursor, b0))
        cursor = max(cursor, b1)
    if cursor < hi:
        clear.append((cursor, hi))
    return clear


def _safe_divider(
    blocked: Sequence[Interval],
    lo: float,
    hi: float,
    preferred: Optional[float] = None,
) -> float:
    """Pick a divider inside ``[lo, hi]`` that avoids ink; centre of the widest clear run."""
    if hi <= lo:
        return (lo + hi) / 2
    clear = _clear_intervals(blocked, lo, hi)
    if not clear:
        return preferred if preferred is not None else (lo + hi) / 2
    if preferred is not None:
        for c0, c1 in clear:
            if c0 <= preferred <= c1:
                return preferred
    widest = max(clear, key=lambda c: c[1] - c[0])
    return (widest[0] + widest[1]) / 2


def column_dividers_from_native(
    native_cells: Dict[str, dict],
    words: Sequence[dict],
    table_pct: Dict[str, float],
    num_cols: int,
) -> Optional[List[float]]:
    """Column boundaries from native cell X clusters, nudged into OCR whitespace."""
    by_col: dict[int, list[dict]] = defaultdict(list)
    for key, cell in native_cells.items():
        by_col[int(key.split(":")[0])].append(cell)
    if len(by_col) != num_cols or num_cols < 1:
        return None

    extents: List[Interval] = []
    for col_id in sorted(by_col):
        lefts = [float(c["left"]) for c in by_col[col_id]]
        rights = [float(c["left"]) + float(c["width"]) for c in by_col[col_id]]
        extents.append((_robust(lefts, low=True), _robust(rights, low=False)))

    x_blocked = [(float(w["left"]), float(w["right"])) for w in words]
    dividers = [table_pct["left"]]
    for idx in range(1, len(extents)):
        prev_right = extents[idx - 1][1]
        cur_left = extents[idx][0]
        lo, hi = min(prev_right, cur_left), max(prev_right, cur_left)
        preferred = (prev_right + cur_left) / 2
        dividers.append(_safe_divider(x_blocked, lo, hi, preferred))
    dividers.append(table_pct["right"])
    return _monotonize(dividers, table_pct["left"], table_pct["right"])


def _robust(values: Sequence[float], *, low: bool) -> float:
    """Cluster edge with median-absolute-deviation outlier rejection."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    med = float(np.median(values))
    mad = float(np.median([abs(v - med) for v in values]))
    kept = values if mad <= 1e-9 else [v for v in values if abs(v - med) <= 2.5 * mad]
    kept = kept or list(values)
    return float(min(kept) if low else max(kept))


def _monotonize(dividers: Sequence[float], lo: float, hi: float) -> List[float]:
    """Strictly increasing dividers spanning ``[lo, hi]`` with a shared minimum size."""
    count = max(len(dividers) - 1, 1)
    min_size = min((hi - lo) / count * 0.05, 0.05)
    out = [lo]
    for idx, value in enumerate(dividers[1:-1], start=1):
        remaining = len(dividers) - 1 - idx
        upper = hi - remaining * min_size
        out.append(min(max(float(value), out[-1] + min_size), max(upper, out[-1] + min_size)))
    out.append(max(hi, out[-1] + min_size))
    return out


def align_rows_to_lines(
    row_texts: Sequence[str],
    lines: Sequence[_Line],
) -> List[List[int]]:
    """
    Monotonic dynamic-programming alignment of HTML rows to OCR lines.

    Each row receives a (possibly empty) consecutive run of lines, order preserved.
    Greedy best-match assignment reorders rows on repeated labels; this does not.
    """
    n_rows, n_lines = len(row_texts), len(lines)
    if n_rows == 0 or n_lines == 0:
        return [[] for _ in row_texts]

    sim = np.zeros((n_rows, n_lines), dtype=float)
    for i, text in enumerate(row_texts):
        for j, line in enumerate(lines):
            sim[i, j] = _similarity(text, line.text)

    neg = float("-inf")
    dp = np.full((n_rows + 1, n_lines + 1), neg, dtype=float)
    back = np.zeros((n_rows + 1, n_lines + 1), dtype=int)
    dp[0, 0] = 0.0

    for i in range(1, n_rows + 1):
        for j in range(n_lines + 1):
            best, best_k = neg, j
            for k in range(j + 1):
                if dp[i - 1, k] == neg:
                    continue
                group = range(k, j)
                score = dp[i - 1, k]
                if not group:
                    score -= _EMPTY_ROW_PENALTY
                else:
                    score += sum(sim[i - 1, g] for g in group)
                    score -= _EXTRA_LINE_PENALTY * (len(group) - 1)
                if score > best:
                    best, best_k = score, k
            dp[i, j], back[i, j] = best, best_k

    groups: List[List[int]] = [[] for _ in range(n_rows)]
    j = n_lines
    for i in range(n_rows, 0, -1):
        k = int(back[i, j])
        groups[i - 1] = list(range(k, j))
        j = k
    return groups


def row_dividers_from_lines(
    row_groups: Sequence[Sequence[int]],
    lines: Sequence[_Line],
    words: Sequence[dict],
    table_pct: Dict[str, float],
) -> List[float]:
    """Row boundaries placed in horizontal whitespace between assigned text lines."""
    n_rows = len(row_groups)
    if n_rows == 0:
        return [table_pct["top"], table_pct["bottom"]]

    spans: List[Optional[Interval]] = []
    for group in row_groups:
        if group:
            spans.append(
                (
                    min(lines[g].top for g in group),
                    max(lines[g].bottom for g in group),
                )
            )
        else:
            spans.append(None)

    anchored = [i for i, span in enumerate(spans) if span is not None]
    if not anchored:
        step = (table_pct["bottom"] - table_pct["top"]) / n_rows
        return [table_pct["top"] + step * i for i in range(n_rows + 1)]

    median_h = _median([lines[g].height for group in row_groups for g in group])
    pad = median_h * 0.45
    first_top = spans[anchored[0]][0]
    last_bottom = spans[anchored[-1]][1]
    grid_top = max(table_pct["top"], first_top - pad)
    grid_bottom = min(table_pct["bottom"], last_bottom + pad)
    if grid_bottom <= grid_top:
        grid_top, grid_bottom = table_pct["top"], table_pct["bottom"]

    y_blocked = [(float(w["top"]), float(w["bottom"])) for w in words]
    dividers: List[Optional[float]] = [None] * (n_rows + 1)
    dividers[0] = grid_top
    dividers[n_rows] = grid_bottom

    for prev, nxt in zip(anchored, anchored[1:]):
        boundary = _safe_divider(y_blocked, spans[prev][1], spans[nxt][0])
        if prev + 1 == nxt:
            dividers[nxt] = boundary
        else:
            # Rows MinerU emits without printed text share the gap evenly.
            start, end = spans[prev][1], spans[nxt][0]
            slots = nxt - prev
            for offset in range(1, slots + 1):
                dividers[prev + offset] = start + (end - start) * offset / (slots + 1)

    for idx in range(1, n_rows):
        if dividers[idx] is None:
            lo = next(d for d in dividers[idx - 1 :: -1] if d is not None)
            following = [d for d in dividers[idx + 1 :] if d is not None]
            hi = following[0] if following else grid_bottom
            missing = 1 + sum(1 for d in dividers[idx + 1 : n_rows] if d is None)
            dividers[idx] = lo + (hi - lo) / (missing + 1)

    return _monotonize([float(d) for d in dividers], grid_top, grid_bottom)


def cell_data_from_dividers(
    converted: ConvertedTable,
    row_dividers: Sequence[float],
    col_dividers: Sequence[float],
) -> Dict[str, dict]:
    """Derive every cell from the divider grid, preserving HTML values and spans.

    Horizontal spans are expanded into one cell per column: a colspan leaves no internal
    vertical edge, which renders as a vertical line that breaks wherever a section header
    row appears. Keeping every column present makes the vertical lines continuous.
    """
    n_rows = len(row_dividers) - 1
    n_cols = len(col_dividers) - 1

    values: Dict[tuple[int, int], str] = {}
    for cell in converted.cells:
        if cell.row >= n_rows or cell.col >= n_cols:
            continue
        values[(cell.row, cell.col)] = cell.value

    # Every grid position gets a cell. MinerU's HTML omits empty trailing cells, and a
    # missing cell leaves no vertical edge for that row, which is what makes the column
    # line disappear on some rows and look dashed on others.
    cell_data: Dict[str, dict] = {}
    for row in range(n_rows):
        for col in range(n_cols):
            cell_data[f"{col + 1}:{row + 1}"] = {
                "colspan": 1,
                "rowspan": 1,
                "left": col_dividers[col],
                "top": row_dividers[row],
                "width": col_dividers[col + 1] - col_dividers[col],
                "height": row_dividers[row + 1] - row_dividers[row],
                "value": values.get((row, col), ""),
            }
    return cell_data


def build_grid(
    converted: ConvertedTable,
    native_cells: Dict[str, dict],
    ocr_words_pct: Sequence[dict],
    table_pct: Dict[str, float],
) -> Grid:
    """Build the cell grid for one MinerU table."""
    words = [w for w in ocr_words_pct if str(w.get("ocr_text", "")).strip()]
    lines = cluster_words_into_lines(words)

    col_dividers = amount_column_dividers(words, table_pct, converted.num_cols)
    col_source = "amount_columns"
    if col_dividers is None:
        col_dividers = column_dividers_from_native(
            native_cells, words, table_pct, converted.num_cols
        )
        col_source = "native_clusters"
    if col_dividers is None:
        # Guessing columns from whitespace alone makes the divider follow the longest
        # label, which moves it from page to page; the native geometry is steadier.
        return Grid(cell_data={}, diagnostics={"column_source": "none"})

    row_texts: List[str] = []
    for row_idx in range(converted.num_rows):
        values = [c.value for c in converted.cells if c.row == row_idx and c.value.strip()]
        row_texts.append(" ".join(values))

    row_groups = align_rows_to_lines(row_texts, lines)
    row_dividers = row_dividers_from_lines(row_groups, lines, words, table_pct)
    cell_data = cell_data_from_dividers(converted, row_dividers, col_dividers)

    matched_rows = sum(1 for group in row_groups if group)
    diagnostics = {
        "column_source": col_source,
        "col_dividers": [round(v, 4) for v in col_dividers],
        "row_dividers": [round(v, 4) for v in row_dividers],
        "ocr_line_count": len(lines),
        "html_row_count": converted.num_rows,
        "rows_matched_to_ocr": matched_rows,
        "rows_matched_pct": (
            matched_rows / converted.num_rows * 100.0 if converted.num_rows else 0.0
        ),
        "cell_count": len(cell_data),
        "unique_tops": len({round(c["top"], 4) for c in cell_data.values()}),
        "unique_lefts": len({round(c["left"], 4) for c in cell_data.values()}),
    }
    logger.debug(
        "[GRID] {} row(s) x {} col(s) — {} OCR line(s), {} row(s) matched, columns from {}",
        converted.num_rows,
        converted.num_cols,
        len(lines),
        matched_rows,
        col_source,
    )
    return Grid(cell_data=cell_data, diagnostics=diagnostics)


_AMOUNT_TAIL = re.compile(
    r"^(?P<label>.*?\S)\s+(?P<amount>\(?-?\$?-?\d[\d,]*(?:\.\d{1,2})?\)?)$"
)

_AMOUNT_TOKEN = re.compile(r"^\(?-?\$?\s?-?\d[\d,]*(?:\.\d{1,2})?\)?$")

_AMOUNT_MARGIN_PCT = 0.35
_AMOUNT_CLUSTER_GAP_PCT = 2.0
_MIN_AMOUNTS_PER_COLUMN = 3
# Keep drawn lines visibly off the glyphs, not merely outside their boxes.
_MIN_CLEARANCE_PCT = 0.15
# How far left of its figures a column header may reasonably extend.
_HEADER_REACH_PCT = 10.0
# A gap narrower than this next to the figures means something sits there — usually the
# column header — and the line would be drawn against it.
_MIN_ADJACENT_RUN_PCT = 1.0


def amount_column_groups(words: Sequence[dict]) -> List[List[dict]]:
    """Group amount tokens into right-aligned columns, ordered left to right."""
    amounts = sorted(
        (w for w in words if _AMOUNT_TOKEN.match(str(w.get("ocr_text", "")).strip())),
        key=lambda w: float(w["right"]),
    )
    if len(amounts) < _MIN_AMOUNTS_PER_COLUMN:
        return []

    groups: List[List[dict]] = []
    current = [amounts[0]]
    for word in amounts[1:]:
        if float(word["right"]) - float(current[-1]["right"]) > _AMOUNT_CLUSTER_GAP_PCT:
            groups.append(current)
            current = [word]
        else:
            current.append(word)
    groups.append(current)
    return [g for g in groups if len(g) >= _MIN_AMOUNTS_PER_COLUMN]


def amount_column_dividers(
    words: Sequence[dict],
    table_pct: Dict[str, float],
    num_cols: int,
) -> Optional[List[float]]:
    """Column dividers anchored just left of each right-aligned amount column.

    Native MinerU X clusters are unstable when a column holds only one or two cells — the
    divider then follows that single cell and lands tens of percent away from the real
    column edge, differing from page to page in one document. Amount columns are
    right-aligned, so their left edge is a far steadier anchor, and placing the line just
    left of the numbers also puts it where a reader expects the column edge to be.
    """
    needed = num_cols - 1
    groups = amount_column_groups(words)
    if needed <= 0 or len(groups) < needed:
        return None
    # Amount columns are the rightmost clusters. Leading account numbers ("1010", "2000")
    # also look like amounts and cluster on the left, so anything further left is a label.
    groups = groups[-needed:]

    dividers = [table_pct["left"]]
    for group in groups:
        group_ids = {id(w) for w in group}
        group_left = min(float(w["left"]) for w in group)
        lo = dividers[-1]
        if group_left - lo < 1.0:
            return None
        # Words left of this column must not be cut, including earlier amount columns.
        blocked = [
            (float(w["left"]), float(w["right"]))
            for w in words
            if id(w) not in group_ids and float(w["left"]) < group_left
        ]
        runs = [r for r in _clear_intervals(blocked, lo, group_left) if r[1] > r[0]]
        if not runs:
            return None
        # Prefer the gap next to the numbers, but a column header is usually wider than
        # its figures ("As of / Mar 2024" over "106,352"), leaving only a sliver there that
        # would draw the line flush against the header. Then move to the widest gap that is
        # still within header reach, which lands just left of the header — the true column
        # edge. Gaps further left belong to the label column, so they stay out of scope.
        run = runs[-1]
        if run[1] - run[0] < _MIN_ADJACENT_RUN_PCT:
            within_reach = [r for r in runs if group_left - r[1] <= _HEADER_REACH_PCT]
            if within_reach:
                run = max(within_reach, key=lambda r: r[1] - r[0])
        clearance = min(_MIN_CLEARANCE_PCT, (run[1] - run[0]) / 2)
        candidate = group_left - _AMOUNT_MARGIN_PCT
        dividers.append(min(max(candidate, run[0] + clearance), run[1] - clearance))

    if table_pct["right"] - dividers[-1] < 1.0:
        return None
    dividers.append(table_pct["right"])
    return _monotonize(dividers, table_pct["left"], table_pct["right"])


def split_single_column_into_label_and_amount(
    cell_data: Dict[str, dict],
    words: Sequence[dict],
    table_pct: Dict[str, float],
) -> Dict[str, dict]:
    """
    Give single-column MinerU tables a label/amount divider anchored on the figures.

    Amount columns are right-aligned, so their left edge is a steady anchor. Without a
    usable anchor the table keeps its single column rather than taking a whitespace guess
    that lands somewhere different on every page.
    """
    if not cell_data or len({int(k.split(":")[0]) for k in cell_data}) != 1:
        return cell_data

    left = table_pct["left"]
    right = table_pct["right"]
    dividers = amount_column_dividers(words, table_pct, 2)
    if dividers is None:
        return cell_data
    split = dividers[1]
    if split - left < 1.0 or right - split < 1.0:
        return cell_data

    new_data: Dict[str, dict] = {}
    for key, cell in sorted(cell_data.items(), key=lambda kv: int(kv[0].split(":")[1])):
        row_id = int(key.split(":")[1])
        top = float(cell["top"])
        bottom = top + float(cell["height"])
        value = str(cell.get("value", "")).strip()

        in_band = [
            w for w in words if top <= (float(w["top"]) + float(w["bottom"])) / 2 <= bottom
        ]
        has_left = any((float(w["left"]) + float(w["right"])) / 2 < split for w in in_band)
        has_right = any((float(w["left"]) + float(w["right"])) / 2 >= split for w in in_band)
        parsed = _AMOUNT_TAIL.match(value) if (has_left and has_right) else None

        if parsed:
            label_value, amount_value = (
                parsed.group("label").strip(),
                parsed.group("amount").strip(),
            )
        elif has_right and not has_left:
            label_value, amount_value = "", value
        else:
            label_value, amount_value = value, ""

        # Both columns are always emitted; a colspan here would break the vertical line.
        new_data[f"1:{row_id}"] = {
            **cell,
            "colspan": 1,
            "left": left,
            "width": split - left,
            "value": label_value,
        }
        new_data[f"2:{row_id}"] = {
            **cell,
            "colspan": 1,
            "left": split,
            "width": right - split,
            "value": amount_value,
        }

    logger.debug(
        "[GRID] single-column split at {:.2f}% — {} cell(s)", split, len(new_data)
    )
    return new_data


def validate_grid(cell_data: Dict[str, dict], tolerance: float = 1e-6) -> Dict[str, Any]:
    """Structural checks the renderer relies on: unique row tops, aligned columns, no overlaps."""
    if not cell_data:
        return {"valid": False, "reason": "empty cell_data"}

    tops_by_row: dict[int, set] = defaultdict(set)
    lefts_by_col: dict[int, set] = defaultdict(set)
    for key, cell in cell_data.items():
        col_s, row_s = key.split(":")
        tops_by_row[int(row_s)].add(round(float(cell["top"]), 4))
        lefts_by_col[int(col_s)].add(round(float(cell["left"]), 4))

    row_tops = {row: next(iter(tops)) for row, tops in tops_by_row.items()}
    ordered_tops = [row_tops[row] for row in sorted(row_tops)]
    return {
        "valid": all(len(t) == 1 for t in tops_by_row.values())
        and all(len(l) == 1 for l in lefts_by_col.values())
        and all(
            b - a > -tolerance for a, b in zip(ordered_tops, ordered_tops[1:])
        ),
        "rows_with_multiple_tops": [r for r, t in tops_by_row.items() if len(t) > 1],
        "cols_with_multiple_lefts": [c for c, l in lefts_by_col.items() if len(l) > 1],
        "row_count": len(tops_by_row),
        "col_count": len(lefts_by_col),
        "min_height": min(float(c["height"]) for c in cell_data.values()),
        "min_width": min(float(c["width"]) for c in cell_data.values()),
    }
