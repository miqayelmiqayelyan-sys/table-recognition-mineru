"""End-to-end MinerU document → TableField pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING

from loguru import logger

from table_recognition_mineru.config import AppConfig
from table_recognition_mineru.geometry_diagnostics import verify_grid_against_page_ocr
from table_recognition_mineru.diagnostics import DiagnosticsWriter
from table_recognition_mineru.document_parser import resolve_pdf_path
from table_recognition_mineru.mineru_adapter import MinerUAdapter, MinerUParseResult
from table_recognition_mineru.ocr_utils import (
    extract_page_ocr_words_pct,
    extract_table_ocr_words_pct,
)
from table_recognition_mineru.output_builder import (
    converted_table_to_table_field,
    mineru_bbox_to_page_pct,
)
from table_recognition_mineru.table_converter import convert_mineru_table
from table_recognition_mineru.table_extractor import extract_tables_from_parse_result

if TYPE_CHECKING:
    from pycognaize.document import Document, Page
    from pycognaize.document.field import TableField


@dataclass
class PipelineTiming:
    mineru_seconds: float = 0.0
    adapter_seconds: float = 0.0
    total_seconds: float = 0.0


@dataclass
class PipelineResult:
    tables: List["TableField"] = field(default_factory=list)
    mineru_result: Optional[MinerUParseResult] = None
    converted_tables: list[dict[str, Any]] = field(default_factory=list)
    timing: PipelineTiming = field(default_factory=PipelineTiming)
    pdf_path: Optional[Path] = None


class MinerUPipeline:
    """Parse a full PDF with MinerU and emit table fields."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or AppConfig.from_yaml()
        self.adapter = MinerUAdapter(self.config.mineru)
        self.diagnostics = DiagnosticsWriter(self.config)

    def process_pdf(self, pdf_path: Path, pages: Optional[dict[int, "Page"]] = None) -> PipelineResult:
        t0 = time.perf_counter()
        pdf_path = Path(pdf_path).resolve()
        parse_output = self.config.output_root / "mineru" / pdf_path.stem

        t_mineru = time.perf_counter()
        mineru_result = self.adapter.parse_pdf(pdf_path, parse_output)
        mineru_seconds = time.perf_counter() - t_mineru

        if self.config.pipeline.debug:
            self.diagnostics.write_json(
                self.diagnostics.parsed_dir,
                f"{pdf_path.stem}_content_list.json",
                mineru_result.load_content_list(),
            )
            self.diagnostics.write_json(
                self.diagnostics.parsed_dir,
                f"{pdf_path.stem}_middle.json",
                mineru_result.load_middle_json(),
            )
            self.diagnostics.copy_raw_tree(mineru_result, self.diagnostics.raw_dir / pdf_path.stem)

        blocks = extract_tables_from_parse_result(mineru_result)
        native_geometries = mineru_result.native_table_geometry
        logger.info(
            "[PIPE] MinerU found {} table block(s), native geometry {} capture(s)",
            len(blocks),
            len(native_geometries),
        )

        converted_payloads: list[dict[str, Any]] = []
        table_fields: List["TableField"] = []

        page_lookup = pages or {}
        page_words_cache: dict[int, list] = {}

        for block in blocks:
            converted = convert_mineru_table(block)
            payload = {
                "index": block.index,
                "page_idx": block.page_idx,
                "page_number": block.page_number,
                "bbox_norm": block.bbox_norm,
                "table_pct": mineru_bbox_to_page_pct(block.bbox_norm),
                "num_rows": converted.num_rows,
                "num_cols": converted.num_cols,
                "cells": [
                    {
                        "row": cell.row,
                        "col": cell.col,
                        "value": cell.value,
                        "rowspan": cell.rowspan,
                        "colspan": cell.colspan,
                    }
                    for cell in converted.cells
                ],
                "table_caption": block.table_caption,
                "source": block.source,
            }
            converted_payloads.append(payload)

            page = page_lookup.get(block.page_number)
            ocr_words: Optional[list] = None
            if page is not None:
                table_pct = mineru_bbox_to_page_pct(block.bbox_norm)
                ocr_words = extract_table_ocr_words_pct(page, table_pct)
                logger.debug(
                    "[PIPE] table {} page {} — {} OCR word(s) in MinerU bbox",
                    block.index,
                    block.page_number,
                    len(ocr_words),
                )

            native_geometry = (
                native_geometries[block.index]
                if block.index < len(native_geometries)
                else None
            )

            if self.config.pipeline.debug:
                self.diagnostics.write_json(
                    self.diagnostics.tables_dir,
                    f"table_{block.index}_page{block.page_number}.json",
                    payload,
                )

            if not page_lookup:
                continue

            geom_meta: list[dict] = []
            table_field = converted_table_to_table_field(
                converted,
                page_lookup,
                ocr_words=ocr_words,
                native_geometry=native_geometry,
                geometry_meta_out=geom_meta,
            )
            if table_field is None:
                continue
            table_fields.append(table_field)

            if self.config.pipeline.debug:
                self.diagnostics.write_json(
                    self.diagnostics.final_dir,
                    f"table_{block.index}_page{block.page_number}_cell_data.json",
                    table_field.tags[0].cell_data,
                )
                self.diagnostics.write_json(
                    self.diagnostics.final_dir,
                    f"table_{block.index}_page{block.page_number}_geometry.json",
                    geom_meta[0] if geom_meta else {},
                )

            if page is not None:
                self._verify_uploaded_geometry(
                    table_field,
                    page,
                    page_words_cache,
                    block.index,
                    block.page_number,
                )

        table_fields.sort(key=lambda tf: (tf.tags[0].page.page_number, tf.tags[0].top))

        total_seconds = time.perf_counter() - t0
        timing = PipelineTiming(
            mineru_seconds=mineru_seconds,
            adapter_seconds=total_seconds - mineru_seconds,
            total_seconds=total_seconds,
        )
        logger.info(
            "[PIPE] complete — {} TableField(s), mineru {:.1f}s total {:.1f}s",
            len(table_fields),
            mineru_seconds,
            total_seconds,
        )
        return PipelineResult(
            tables=table_fields,
            mineru_result=mineru_result,
            converted_tables=converted_payloads,
            timing=timing,
            pdf_path=pdf_path,
        )

    def _verify_uploaded_geometry(
        self,
        table_field: "TableField",
        page: "Page",
        page_words_cache: dict[int, list],
        table_index: int,
        page_number: int,
    ) -> None:
        """Log whether the geometry about to be uploaded draws any line through text."""
        try:
            cell_data = table_field.tags[0].cell_data
        except Exception:  # TableTag.cell_data raises a bare Exception when empty
            return
        if page_number not in page_words_cache:
            page_words_cache[page_number] = extract_page_ocr_words_pct(page)
        report = verify_grid_against_page_ocr(cell_data, page_words_cache[page_number])
        grazes = len(report["horizontal_grazes"]) + len(report["vertical_grazes"])
        if report["clean"]:
            logger.info(
                "[VERIFY] table {} page {} clean — {} horizontal / {} vertical edge(s), "
                "no line through text ({} sitting against OCR box padding)",
                table_index,
                page_number,
                report["horizontal_edges"],
                report["vertical_edges"],
                grazes,
            )
            return
        logger.error(
            "[VERIFY] table {} page {} BAD — {} horizontal and {} vertical edge(s) cut text",
            table_index,
            page_number,
            len(report["horizontal_cuts"]),
            len(report["vertical_cuts"]),
        )
        for cut in report["horizontal_cuts"] + report["vertical_cuts"]:
            logger.error(
                "[VERIFY]   at {:.4f}% cuts: {}",
                cut["position"],
                " | ".join(cut["words"][:6]),
            )
        if grazes:
            logger.warning(
                "[VERIFY] table {} page {} — {} further edge(s) clear the text but sit "
                "against its OCR box padding",
                table_index,
                page_number,
                grazes,
            )

    def process_document(self, document: "Document") -> PipelineResult:
        document.load_page_images()
        document.load_ocr()
        pdf_path = resolve_pdf_path(document=document)
        page_lookup = {int(n): document.pages[n] for n in document.pages}
        return self.process_pdf(pdf_path, pages=page_lookup)
