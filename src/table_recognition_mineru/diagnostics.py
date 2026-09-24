"""Persist MinerU pipeline diagnostics to disk."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from table_recognition_mineru.config import AppConfig

if TYPE_CHECKING:
    from table_recognition_mineru.mineru_adapter import MinerUParseResult


class DiagnosticsWriter:
    """Write raw/parsed/table/final artifacts under output/."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.root = config.output_root
        subs = config.pipeline.diagnostics_subdirs
        self.raw_dir = self.root / subs["raw"]
        self.parsed_dir = self.root / subs["parsed"]
        self.tables_dir = self.root / subs["tables"]
        self.final_dir = self.root / subs["final"]
        if config.pipeline.debug:
            for path in (self.raw_dir, self.parsed_dir, self.tables_dir, self.final_dir):
                path.mkdir(parents=True, exist_ok=True)

    def write_json(self, subdir: Path, name: str, payload: Any) -> Path:
        path = subdir / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("[DIAG] wrote {}", path)
        return path

    def write_text(self, subdir: Path, name: str, text: str) -> Path:
        path = subdir / name
        path.write_text(text, encoding="utf-8")
        logger.debug("[DIAG] wrote {}", path)
        return path

    def copy_raw_tree(self, result: "MinerUParseResult", dest: Path) -> None:
        src = result.output_dir.resolve()
        dest = dest.resolve()
        if not src.is_dir():
            return
        if dest.exists():
            shutil.rmtree(dest)

        def _ignore(dir_path: str, names: list[str]) -> set[str]:
            ignored: set[str] = set()
            for name in names:
                candidate = (Path(dir_path) / name).resolve()
                if candidate == dest or dest.is_relative_to(candidate):
                    ignored.add(name)
            return ignored

        shutil.copytree(src, dest, ignore=_ignore)
        logger.debug("[DIAG] copied MinerU tree to {}", dest)
