"""Convert MinerU table HTML into a logical cell grid."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from bs4 import BeautifulSoup
from loguru import logger

from table_recognition_mineru.table_extractor import MinerUTableBlock

# A column holding only these is a currency/sign marker column, not a column of its own:
# MinerU frequently splits "$ (973,468)" into a "$ (" cell and a "973,468)" cell.
_MARKER_ONLY = re.compile(r"^[$()\-\s]*$")


@dataclass
class ConvertedCell:
    row: int
    col: int
    value: str
    rowspan: int = 1
    colspan: int = 1


@dataclass
class ConvertedTable:
    source: MinerUTableBlock
    num_rows: int
    num_cols: int
    cells: List[ConvertedCell] = field(default_factory=list)


def convert_mineru_table(block: MinerUTableBlock) -> ConvertedTable:
    """Parse MinerU ``table_body`` HTML into anchor cells with spans."""
    soup = BeautifulSoup(block.table_body_html, "html.parser")
    table = soup.find("table")
    if table is None:
        return ConvertedTable(source=block, num_rows=0, num_cols=0, cells=[])

    rows = table.find_all("tr")
    if not rows:
        return ConvertedTable(source=block, num_rows=0, num_cols=0, cells=[])

    max_cols = 0
    for row in rows:
        width = sum(int(cell.get("colspan", 1)) for cell in row.find_all(["td", "th"]))
        max_cols = max(max_cols, width)

    occupied = [[False] * max_cols for _ in range(len(rows))]
    cells: List[ConvertedCell] = []

    for row_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(["td", "th"]):
            while col_idx < max_cols and occupied[row_idx][col_idx]:
                col_idx += 1
            if col_idx >= max_cols:
                break

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            value = cell.get_text(separator=" ", strip=True)
            cells.append(
                ConvertedCell(
                    row=row_idx,
                    col=col_idx,
                    value=value,
                    rowspan=rowspan,
                    colspan=colspan,
                )
            )
            for dr in range(rowspan):
                for dc in range(colspan):
                    r = row_idx + dr
                    c = col_idx + dc
                    if r < len(occupied) and c < max_cols:
                        occupied[r][c] = True
            col_idx += colspan

    return merge_marker_columns(
        ConvertedTable(
            source=block,
            num_rows=len(rows),
            num_cols=max_cols,
            cells=cells,
        )
    )


def merge_marker_columns(table: ConvertedTable) -> ConvertedTable:
    """Fold currency-marker and empty columns into the column they belong to.

    A page has one visible boundary per real column, but MinerU's HTML often puts the
    ``$`` and the ``(`` of a negative number in columns of their own and leaves a trailing
    empty column. Asking for a divider per HTML column then demands more boundaries than
    the page has gaps, so no column anchor fits and the table falls back to the jittery
    native geometry. Merging them first makes the HTML count match what is printed.
    """
    if table.num_cols < 2 or not table.cells:
        return table

    values_by_col: Dict[int, List[str]] = {c: [] for c in range(table.num_cols)}
    for cell in table.cells:
        if cell.colspan == 1 and cell.col in values_by_col:
            values_by_col[cell.col].append(cell.value)

    def _carries_content(col: int) -> bool:
        return any(not _MARKER_ONLY.match(v or "") for v in values_by_col.get(col) or [])

    def _is_currency_marker(col: int) -> bool:
        values = [v for v in values_by_col.get(col) or [] if v.strip()]
        return bool(values) and all(_MARKER_ONLY.match(v) for v in values)

    has_currency_markers = any(
        _is_currency_marker(col) for col in range(table.num_cols)
    )
    if not has_currency_markers:
        return table

    keep = [col for col in range(table.num_cols) if col == 0 or _carries_content(col)]
    if len(keep) == table.num_cols:
        return table

    # A marker belongs to the figure on its right ("$" then "973,468"), so merge that way
    # and only fall back to the left for a trailing column with nothing after it.
    target: Dict[int, int] = {}
    for col in range(table.num_cols):
        to_right = [i for i, k in enumerate(keep) if k >= col]
        to_left = [i for i, k in enumerate(keep) if k <= col]
        target[col] = to_right[0] if to_right else to_left[-1]

    merged: Dict[tuple[int, int], ConvertedCell] = {}
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        col = target.get(cell.col, 0)
        spanned = {target[c] for c in range(cell.col, cell.col + cell.colspan) if c in target}
        colspan = max(1, len(spanned))
        key = (cell.row, col)
        existing = merged.get(key)
        if existing is None:
            merged[key] = ConvertedCell(
                row=cell.row,
                col=col,
                value=cell.value,
                rowspan=cell.rowspan,
                colspan=colspan,
            )
            continue
        joined = " ".join(part for part in (existing.value, cell.value) if part).strip()
        existing.value = joined
        existing.rowspan = max(existing.rowspan, cell.rowspan)
        existing.colspan = max(existing.colspan, colspan)

    logger.debug(
        "[CONVERT] merged {} marker/empty column(s): {} → {} column(s)",
        table.num_cols - len(keep),
        table.num_cols,
        len(keep),
    )
    return ConvertedTable(
        source=table.source,
        num_rows=table.num_rows,
        num_cols=len(keep),
        cells=list(merged.values()),
    )
