# table-recognition-mineru

Turn PDF tables into **stable grid geometry** and **cell values** using [MinerU](https://github.com/opendatalab/MinerU) for structure and page OCR to place row/column lines in whitespace—not through text.

## What you get

| Input | Output |
|-------|--------|
| Full PDF (any page count) | One table per MinerU table block |
| MinerU HTML (rows, values, spans) | Rectangular `cell_data` in **page %** |
| Page OCR | Dividers aligned to text lines and amount columns |

Each cell carries `left`, `top`, `width`, `height`, `value`, and span metadata suitable for downstream table rendering.

## How it works

```
PDF
 → MinerU parse (layout + table HTML + native cell boxes)
 → Table discovery + HTML grid (marker columns merged when MinerU splits "$" / "(")
 → Divider grid: column anchors (amounts → native clusters) + row anchors (OCR lines ↔ HTML rows)
 → Optional self-check against full-page OCR (cuts vs grazes)
 → `cell_data` + table metadata on disk (debug mode)
```

Geometry is built from **shared dividers**, not by nudging each MinerU cell box. That keeps vertical lines continuous, row lines between text, and values identical to MinerU HTML.

Details: [docs/GEOMETRY_PIPELINE.md](docs/GEOMETRY_PIPELINE.md).

## Quick start

```bash
cd table-recognition-mineru
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run on the included sample (first run downloads MinerU models):

```bash
python scripts/run_pdf.py samples/sample_balance_sheet.pdf
```

With `pipeline.debug: true` in `configs/default.yaml`, artifacts land under `output/`:

| Path | Purpose |
|------|---------|
| `output/parsed/` | MinerU JSON |
| `output/tables/` | Converted table structure per block |
| `output/final/` | Final `cell_data` + geometry metadata |
| `output/raw/` | Full MinerU run tree |
| `output/run_summary.json` | Counts and timing from the last run |

Open `output/final/` to inspect grids and values for each detected table.

## Configuration

`configs/default.yaml`:

```yaml
mineru:
  backend: pipeline
  parse_method: auto
  lang: en
  table_enable: true

pipeline:
  debug: true
  output_dir: output
```

- `MINERU_MODEL_SOURCE=huggingface` — use if model download needs an explicit source

**GPU:** ≥8 GB VRAM recommended for multi-page PDFs on the `pipeline` backend; CPU works but is slower.

## Project layout

```
configs/              Default YAML
docs/                 Geometry pipeline (deep dive)
driver.py             Deployed model entry point
scripts/
  run_pdf.py          Local PDF → output/
  audit_grid_vs_page_ocr.py   Grid vs page OCR (see script docstring)
  render_grid_overlay.py      PNG overlay (see script docstring)
src/table_recognition_mineru/
  pipeline.py         End-to-end flow
  divider_grid.py     Column/row dividers + grid cells
  geometry_builder.py Single geometry entry
  table_converter.py  MinerU HTML → logical grid (+ marker merge)
  mineru_adapter.py   MinerU do_parse wrapper
tests/                Unit + integration tests (mock MinerU fixtures)
```

## Example cell

Keys are `"col:row"` (1-based). Coordinates are page percentages (`mineru_bbox / 10` for MinerU’s 0–1000 frame):

```python
{
  "1:1": {
    "left": 6.2, "top": 48.0, "width": 29.4, "height": 4.2,
    "value": "Assets", "colspan": 1, "rowspan": 1
  }
}
```

## Tests

```bash
pytest -q
```

## Docker

```bash
docker build -t table-recognition-mineru .
docker run --gpus all table-recognition-mineru
```

## Stack

| Piece | Choice |
|-------|--------|
| Parser | MinerU 3.x, `pipeline` backend |
| Table structure | MinerU `table_body` HTML |
| Geometry | OCR-anchored divider grid (`divider_grid.py`) |
| Runtime | Python ≥3.10, PyTorch (MinerU dependency) |
