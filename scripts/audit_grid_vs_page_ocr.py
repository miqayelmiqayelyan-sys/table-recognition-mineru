#!/usr/bin/env python3
"""
Audit the produced grid against every OCR word on the page.

``extract_area_words`` only returns words mostly inside the MinerU bbox, so a divider can
look clean against that subset while still cutting a word the viewer renders. This uses
``page.get_ocr_formatted()`` — the same source the viewer shows — and prints each offending edge
with the text it cuts, plus the column geometry per table.

    DOCUMENT_ID=<id> python3 scripts/audit_grid_vs_page_ocr.py
    SNAPSHOT_DIR=/tmp/before ...   # also dump cell_data for regression comparison
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from table_recognition_mineru.config import AppConfig
from table_recognition_mineru.document_parser import resolve_pdf_path
from table_recognition_mineru.geometry_builder import build_cell_data
from table_recognition_mineru.geometry_diagnostics import verify_grid_against_page_ocr
from table_recognition_mineru.mineru_adapter import MinerUAdapter
from table_recognition_mineru.ocr_utils import (
    extract_page_ocr_words_pct,
    extract_table_ocr_words_pct,
)
from table_recognition_mineru.output_builder import sanitize_cell_data_for_table_tag
from table_recognition_mineru.table_coords import mineru_bbox_to_page_pct
from table_recognition_mineru.table_converter import convert_mineru_table
from table_recognition_mineru.table_extractor import extract_tables_from_parse_result


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    document_id = os.environ.get("DOCUMENT_ID", "6a9e93842aaee9842d53fb4e")
    recipe_id = os.environ.get("RECIPE_ID", "5f302bb1298def0012145280")
    snapshot_dir = os.environ.get("SNAPSHOT_DIR")

    from pycognaize.document import Document
    from pycognaize.login import Login

    cfg = AppConfig.from_yaml()
    _load_env_file(PROJECT_ROOT / ".env")
    os.environ.setdefault("API_HOST", cfg.api_host)
    Login().login(os.environ["COGNAIZE_EMAIL"], os.environ["COGNAIZE_PASSWORD"])
    doc = Document.fetch_document(recipe_id, document_id, api_host=cfg.api_host)
    doc.load_page_images()
    doc.load_ocr()
    page_lookup = {int(n): doc.pages[n] for n in doc.pages}

    result = MinerUAdapter(cfg.mineru).parse_pdf(
        resolve_pdf_path(document=doc), cfg.output_root / "mineru" / f"audit_{document_id}"
    )
    blocks = extract_tables_from_parse_result(result)
    native_geometries = result.native_table_geometry

    total_edges = 0
    total_cuts = 0
    for block in blocks:
        page = page_lookup.get(block.page_number)
        if page is None:
            continue
        converted = convert_mineru_table(block)
        table_pct = mineru_bbox_to_page_pct(block.bbox_norm)
        cell_data, meta = build_cell_data(
            converted,
            page=page,
            native_geometry=(
                native_geometries[block.index]
                if block.index < len(native_geometries)
                else None
            ),
            ocr_words_pct=extract_table_ocr_words_pct(page, table_pct),
        )
        cell_data = sanitize_cell_data_for_table_tag(cell_data)
        if not cell_data:
            continue

        if snapshot_dir:
            target = Path(snapshot_dir)
            target.mkdir(parents=True, exist_ok=True)
            name = f"{document_id}_table{block.index}_page{block.page_number}.json"
            (target / name).write_text(
                json.dumps(cell_data, indent=2, sort_keys=True), encoding="utf-8"
            )

        report = verify_grid_against_page_ocr(cell_data, extract_page_ocr_words_pct(page))
        cuts = report["horizontal_cuts"] + report["vertical_cuts"]
        grazes = report["horizontal_grazes"] + report["vertical_grazes"]
        total_edges += report["horizontal_edges"] + report["vertical_edges"]
        total_cuts += len(cuts)

        col_lefts = sorted({round(float(c["left"]), 2) for c in cell_data.values()})
        rows = len({round(float(c["top"]), 4) for c in cell_data.values()})
        merged = sum(1 for c in cell_data.values() if int(c.get("colspan", 1)) > 1)
        print(
            f"table {block.index} page {block.page_number}: "
            f"{report['horizontal_edges']} horizontal + {report['vertical_edges']} "
            f"vertical edge(s), {len(cuts)} cutting text, {len(grazes)} against box padding"
        )
        print(
            f"    columns at {col_lefts} from "
            f"{meta.get('grid_diagnostics', {}).get('column_source', 'n/a')}, "
            f"path={meta.get('grid_selected', 'n/a')}"
        )
        print(
            f"    {rows} row(s), {merged} merged cell(s), {len(cell_data)} cell(s), "
            f"complete grid: {len(cell_data) == rows * len(col_lefts)}"
        )
        for cut in cuts:
            print(f"    at {cut['position']:8.4f}%  cuts: {' | '.join(cut['words'][:6])}")

    print(
        f"TOTAL: {total_cuts}/{total_edges} edges cross text "
        f"({total_cuts / max(total_edges, 1) * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()
