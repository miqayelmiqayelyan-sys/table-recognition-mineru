#!/usr/bin/env python3
"""
Draw the cell grid over the page image for visual verification.

Green = cell boundaries, red = a boundary that cuts or grazes OCR text.

    DOCUMENT_ID=6a9e93842aaee9842d53fb4e python3 scripts/render_grid_overlay.py

Writes output/grid_overlay/page<N>.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import cv2
import numpy as np

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
        resolve_pdf_path(document=doc), cfg.output_root / "mineru" / f"overlay_{document_id}"
    )
    blocks = extract_tables_from_parse_result(result)
    native_geometries = result.native_table_geometry

    canvases: dict[int, np.ndarray] = {}
    summaries: list[str] = []

    for block in blocks:
        page = page_lookup.get(block.page_number)
        if page is None:
            continue
        converted = convert_mineru_table(block)
        table_pct = mineru_bbox_to_page_pct(block.bbox_norm)
        cell_data, _meta = build_cell_data(
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

        canvas = canvases.setdefault(block.page_number, page.image_arr.copy())
        if canvas.ndim == 2:
            canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
            canvases[block.page_number] = canvas
        img_h, img_w = canvas.shape[:2]

        report = verify_grid_against_page_ocr(cell_data, extract_page_ocr_words_pct(page))
        bad_rows = {cut["position"] for cut in report["horizontal_cuts"]}
        bad_cols = {cut["position"] for cut in report["vertical_cuts"]}

        for cell in cell_data.values():
            left, top = float(cell["left"]), float(cell["top"])
            right, bottom = left + float(cell["width"]), top + float(cell["height"])
            bad = (
                round(top, 4) in bad_rows
                or round(bottom, 4) in bad_rows
                or round(left, 4) in bad_cols
                or round(right, 4) in bad_cols
            )
            cv2.rectangle(
                canvas,
                (int(left / 100 * img_w), int(top / 100 * img_h)),
                (int(right / 100 * img_w), int(bottom / 100 * img_h)),
                (0, 0, 255) if bad else (0, 170, 0),
                1,
            )

        summaries.append(
            f"table {block.index} page {block.page_number}: cells={len(cell_data)} "
            f"cuts={len(report['horizontal_cuts'])} horizontal / "
            f"{len(report['vertical_cuts'])} vertical"
        )

    out_dir = cfg.output_root / "grid_overlay"
    out_dir.mkdir(parents=True, exist_ok=True)
    for page_number, canvas in canvases.items():
        path = out_dir / f"page{page_number}.png"
        cv2.imwrite(str(path), canvas)
        print(f"Wrote {path}")
    for line in summaries:
        print(line)


if __name__ == "__main__":
    main()
