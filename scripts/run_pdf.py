#!/usr/bin/env python3
"""Run the MinerU pipeline locally on a PDF (no Genie)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loguru import logger

from table_recognition_mineru.config import AppConfig
from table_recognition_mineru.mineru_adapter import get_mineru_version
from table_recognition_mineru.pipeline import MinerUPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MinerU table extraction on a PDF")
    parser.add_argument("pdf", type=Path, help="Path to input PDF")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config")
    args = parser.parse_args()

    config = AppConfig.from_yaml(args.config)
    logger.info("MinerU package version: {}", get_mineru_version())

    pipeline = MinerUPipeline(config)
    result = pipeline.process_pdf(args.pdf)

    summary = {
        "pdf": str(result.pdf_path),
        "tables_found": len(result.converted_tables),
        "table_fields_built": len(result.tables),
        "mineru_seconds": result.timing.mineru_seconds,
        "total_seconds": result.timing.total_seconds,
        "converted_tables": result.converted_tables,
    }
    out = config.output_root / "run_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nSummary written to {out}")


if __name__ == "__main__":
    main()
