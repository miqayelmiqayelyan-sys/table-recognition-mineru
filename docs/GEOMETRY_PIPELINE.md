# MinerU → table geometry

There is one geometry path. It builds dividers first and derives every cell from them.

## Why a grid

The viewer draws a line at every cell edge, so geometry has to be a *grid*: one X per column
boundary, one Y per row boundary. Nudging each native MinerU cell box individually —
which is what every earlier attempt did — gives per-cell jitter (dashed verticals) and row
bands that drift away from the printed text (horizontal lines through glyphs).

Deriving cells from shared dividers is what structurally guarantees the requirements:

| Requirement | Guaranteed by |
|-------------|---------------|
| Straight vertical lines | one X per column, shared by all rows |
| Horizontal lines between text | dividers placed in OCR whitespace runs |
| All cells closed, no gaps/overlaps | adjacent cells share the same divider value |
| `TableTag` never raises | exactly one `top` per row, one `left` per column |
| Values unchanged | cell text comes from MinerU HTML |

## Pipeline

```
MinerU wireless cell bboxes ─┐
                             ├─► column dividers (amount clusters, then native
Page OCR words ──────────────┘    clusters)                        
                             │
                             ├─► text lines (centre clustering)
                             │        │
                             │        └─► monotonic DP alignment to HTML rows
                             │                     │
                             │                     └─► row dividers in whitespace
                             ▼
                    cell_data = full rectangular grid ─► TableField
```

Entry point: `geometry_builder.build_cell_data`. Implementation:
`src/table_recognition_mineru/divider_grid.py`.

### Column dividers

Two sources, in order, first one that produces a valid set wins (recorded in
`grid_diagnostics.column_source`):

1. **`amount_columns`** — the right-aligned money columns. Amount-like tokens are
   clustered by X, the rightmost `num_cols - 1` clusters are kept (so leading account
   numbers like `1010` are not mistaken for amounts), and the divider goes in the clear
   run to the left of each cluster. If that run is too narrow to read as a gap, the widest
   valid run within header reach is used instead, so the line keeps clearance from
   headings like `Mar 2024`.
2. **`native_clusters`** — MinerU X positions clustered per column with median-absolute-
   deviation outlier rejection, each internal divider moved to the centre of the widest
   ink-free run between the two columns.

Anchoring on amounts first is what keeps the vertical line in the same place from page to
page. There is deliberately no whitespace-valley fallback: picking the widest gap makes the
divider follow the longest label, so it lands somewhere different on every page. With no
anchor the grid stands down and native geometry is used instead.

### Marker columns

MinerU often splits a printed amount into several HTML columns — `"$ ("` then `"973,468"` —
and leaves a trailing empty column. The page still has one visual gap per year, so asking
for a divider per HTML column demands more boundaries than exist, amount anchoring fails,
and the table falls back to jittery native geometry. `merge_marker_columns` folds those
sign/empty columns into the figure they belong to before the grid is built, so the HTML
column count matches what is printed.

### Row dividers

HTML rows are aligned to OCR text lines by **monotonic dynamic programming** rather than
greedy best-match. Greedy matching reorders rows whenever a label repeats (`Total`,
`0.00`); DP keeps reading order and lets one row absorb several wrapped lines or none at
all. Each boundary is then placed at the centre of the ink-free run between the adjacent
rows' text, so a divider can only cross a glyph when two text lines genuinely overlap.

Rows MinerU emits without printed text (spacers) share the surrounding gap evenly, so
row count and topology never change.

### Full rectangular grid

`cell_data_from_dividers` emits a cell for every (row, column) position and expands
`colspan` into individual empty cells. Sparse output — only the cells MinerU's HTML
mentions — leaves vertical lines broken wherever a section header spans the width or a
trailing cell is empty, which is what made the verticals look dashed.

### Single-column tables

Tables whose HTML has one column are split into label/amount by the same amount-column
anchoring, and always emit both cells per row so the divider runs the full height. Without
an amount anchor the table keeps its single column.

### Fallback

The grid needs page OCR. Without OCR, or when `validate_grid` fails, or when no column
anchor is found, the column-snapped native geometry is used and the reason is recorded in
`grid_fallback_reason`. If MinerU captured no native geometry at all the table is skipped
with a warning — uniform geometry would put a line through nearly every row, which is worse
than no table. On the two reference documents (8 tables) the grid path is always selected.

## Verification

`verify_grid_against_page_ocr` checks every edge against **all** page OCR words — not just
the words inside the MinerU bbox, which is a subset a divider can miss while still cutting
text the viewer renders. An edge is only tested along the span it is actually drawn over.

OCR boxes are padded well past the glyphs — on some scans a box is nearly as tall as the
whole row pitch — so the check distinguishes two outcomes. An edge through the inner
`INK_INSET_FRACTION` band is a **cut** and logged as an error; an edge that clears the ink
but sits against the reported box is a **graze** and only counted in a warning. Without that
split the check cried wolf: on one six-table document it reported 49 problems where only 8
were lines through text.

The pipeline runs this on the final grid before export. It logs but does not block — a flagged
table is still written out.

Current result on both reference documents: **0 of 58 edges** cut text on
`6a9e93842aaee9842d53fb4e`, **0 of 256** on `6aab87ebaa31f3c09763b78d`. For reference, the
earlier per-cell approaches crossed text on 64–94% of horizontal edges.

## Commands

```bash
cd table-recognition-mineru && source .venv/bin/activate

python scripts/run_pdf.py samples/sample_balance_sheet.pdf
# → output/final/, output/run_summary.json

pytest -q
```
