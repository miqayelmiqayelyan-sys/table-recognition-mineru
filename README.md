# table-recognition-mineru

Standalone document/table understanding pipeline powered by **MinerU** for Genie integration.

This project is intentionally **separate** from the existing table-recognition stacks (`table-detection-detr`, `ai-core-table-analyzer`, `table-recognition-geo`, `table-recognition-trivia`). Those projects were used only as a reference for:

- Genie model structure
- configuration layout
- how input documents are received
- how `document.y["table"]` is returned

**No recognition algorithms, models, OCR logic, geometry logic, postprocessing, or table reconstruction code were copied from those projects.** The only shared implementation is
`build_table_field`, which encodes the `TableField` contract itself.

## What this project does

```
PDF (full document)
      ↓
   MinerU (official do_parse API)
      ↓
 content_list.json / middle.json
      ↓
 table block discovery
      ↓
 HTML structure + OCR-anchored divider grid → cell_data
      ↓
 verification against page OCR
      ↓
 TableField → document.y["table"]
      ↓
      Genie
```

MinerU is responsible for layout analysis, text extraction, and table structure. This repository only wraps MinerU and converts its table output into the Genie contract.

## Technology

| Component | Value |
|-----------|-------|
| Engine | [MinerU](https://github.com/opendatalab/MinerU) **3.4.5** |
| Default backend | `pipeline` (PP-DocLayoutV2 + PaddleOCR + table structure) |
| Models | `opendatalab/PDF-Extract-Kit-1.0` (auto-downloaded from HuggingFace) |
| Table source | `content_list.json` (`type: "table"`, `table_body` HTML) |
| Fallback | `middle.json` |
| Output | `pycognaize` `TableField` with page-% `cell_data` |

## Installation

```bash
cd table-recognition-mineru
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,genie]"
```

MinerU downloads models on first run (HuggingFace by default). Set `MINERU_MODEL_SOURCE=huggingface` if needed.

### GPU requirements

- **Recommended:** NVIDIA GPU with ≥8 GB VRAM for the `pipeline` backend on multi-page PDFs
- CPU-only runs are possible but significantly slower
- First run includes model download time

## Configuration

Edit `configs/default.yaml`:

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

Environment overrides:

- `PDF_PATH` — local PDF for Genie runs when document storage has no PDF
- `DOCUMENT_ID`, `RECIPE_ID`, `API_HOST`, `X_AUTH_TOKEN` — Genie local runner
- `COGNAIZE_EMAIL`, `COGNAIZE_PASSWORD` — login for `genie_local.py`

Copy `.env.example` to `.env` and fill in credentials. `.env` is gitignored.

## Local inference (no Genie)

```bash
python scripts/run_pdf.py samples/sample_balance_sheet.pdf
```

Or use the helper script:

```bash
./run_local.sh samples/sample_balance_sheet.pdf
```

## Inspecting MinerU output

When `pipeline.debug: true`, diagnostics are written under `output/`:

| Directory | Contents |
|-----------|----------|
| `output/raw/<pdf_stem>/` | Full MinerU artifact tree |
| `output/parsed/` | `*_content_list.json`, `*_middle.json` |
| `output/tables/` | Per-table converted structure |
| `output/final/` | `cell_data` payloads and geometry metadata |
| `output/run_summary.json` | Run timing and table counts |

## Genie integration

```bash
cp .env.example .env   # then fill in credentials
export DOCUMENT_ID=your_document_id
```

Production entry point:

```bash
python driver.py
```

`MinerUTableModel.predict(document)`:

1. Loads page images
2. Resolves PDF from document storage or `PDF_PATH`
3. Runs MinerU
4. Sets `document.y["table"]` to a list of `TableField` objects

## Output contract

Each table becomes a `TableField` with `cell_data` keyed as `"col:row"` (1-based):

```python
{
  "1:1": {
    "left": 6.2, "top": 48.0, "width": 29.4, "height": 4.2,
    "value": "Assets", "colspan": 1, "rowspan": 1
  },
  ...
}
```

Coordinates are **page percentages** derived from MinerU's 0–1000 normalized bbox:

```
page_pct = mineru_coord / 10
```

Cell geometry comes from row/column dividers anchored on page OCR, so every line falls in
whitespace rather than through text — see [docs/GEOMETRY_PIPELINE.md](docs/GEOMETRY_PIPELINE.md).

## Tests

```bash
pytest tests/ -v
```

Unit tests mock MinerU output. One integration test runs the full adapter chain on fixture JSON; run `scripts/run_pdf.py` for a real MinerU end-to-end check.

## Docker

```bash
docker build -t table-recognition-mineru .
docker run --gpus all table-recognition-mineru
```

## MinerU output schema (observed)

From a real run on `samples/sample_balance_sheet.pdf`, MinerU writes `*_content_list.json` as a flat list of blocks:

```json
{
  "type": "table",
  "page_idx": 0,
  "bbox": [122, 184, 875, 367],
  "table_body": "<table><tr><td rowspan=1 colspan=1>Assets</td>...</tr></table>",
  "table_caption": [],
  "table_footnote": [],
  "img_path": "images/....jpg"
}
```

| Field | Meaning |
|-------|---------|
| `bbox` | `[x0, y0, x1, y1]` normalized to **0–1000** page coordinates |
| `page_idx` | 0-based page index |
| `table_body` | HTML table with `rowspan` / `colspan` on each `<td>` |
| `type` | `"table"` for table blocks; also `"text"`, etc. |

Page percentages: `left = bbox[0]/10`, `top = bbox[1]/10`, etc.

Merged cells: MinerU exposes `rowspan` and `colspan` attributes on `<td>` elements (often `rowspan=1 colspan=1` even for normal cells).

## Sample run (CPU, 1-page PDF)

```
MinerU version: 3.4.5
Backend: pipeline
Runtime: ~17s (CPU, first models cached)
Tables found: 1 (8 rows × 3 cols)
GPU: not available in test environment
```

Inspect artifacts under `output/raw/`, `output/parsed/`, `output/tables/`, `output/final/`.

## Why a separate project?

We are evaluating whether MinerU's document understanding can **replace** the custom DETR / TSR / TRivia / OCR-geometry stacks entirely. This repo isolates that experiment without mixing recognition approaches.
