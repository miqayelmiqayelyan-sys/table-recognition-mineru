"""Thin wrapper around the official MinerU parsing API."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from table_recognition_mineru.config import MinerUConfig


@dataclass
class MinerUParseResult:
    """Paths and metadata from a MinerU parse run."""

    pdf_stem: str
    output_dir: Path
    mineru_version: str
    backend: str
    content_list_path: Optional[Path] = None
    middle_json_path: Optional[Path] = None
    content_list_v2_path: Optional[Path] = None
    markdown_path: Optional[Path] = None
    raw_artifacts: dict[str, str] = field(default_factory=dict)
    native_table_geometry: list[dict[str, Any]] = field(default_factory=list)

    def load_content_list(self) -> list[dict[str, Any]]:
        if not self.content_list_path or not self.content_list_path.is_file():
            return []
        return json.loads(self.content_list_path.read_text(encoding="utf-8"))

    def load_middle_json(self) -> dict[str, Any]:
        if not self.middle_json_path or not self.middle_json_path.is_file():
            return {}
        return json.loads(self.middle_json_path.read_text(encoding="utf-8"))


def get_mineru_version() -> str:
    try:
        from importlib.metadata import version

        return version("mineru")
    except Exception:
        try:
            import mineru

            return getattr(mineru, "__version__", "unknown")
        except ImportError:
            return "not installed"


def _find_artifact(base: Path, stem: str, suffix: str) -> Optional[Path]:
    direct = base / f"{stem}{suffix}"
    if direct.is_file():
        return direct
    matches = sorted(base.rglob(f"{stem}{suffix}"))
    return matches[0] if matches else None


class MinerUAdapter:
    """Invoke MinerU ``do_parse`` on a PDF and collect output artifacts."""

    def __init__(self, config: MinerUConfig) -> None:
        self.config = config

    def parse_pdf(self, pdf_path: Path, output_dir: Path) -> MinerUParseResult:
        pdf_path = pdf_path.resolve()
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        stem = pdf_path.stem
        logger.info(
            "[MinerU] parsing {} backend={} lang={}",
            pdf_path.name,
            self.config.backend,
            self.config.lang,
        )

        from mineru.cli.common import do_parse, read_fn

        from table_recognition_mineru.native_geometry_capture import (
            get_captured_geometry,
            install_native_geometry_capture,
            uninstall_native_geometry_capture,
        )

        install_native_geometry_capture()
        pdf_bytes = read_fn(pdf_path)
        try:
            do_parse(
                str(output_dir),
                [stem],
                [pdf_bytes],
                [self.config.lang],
                backend=self.config.backend,
                parse_method=self.config.parse_method,
                formula_enable=self.config.formula_enable,
                table_enable=self.config.table_enable,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_md=True,
                f_dump_middle_json=True,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=True,
                start_page_id=self.config.start_page_id,
                end_page_id=self.config.end_page_id,
            )
        finally:
            native_geometry = get_captured_geometry()
            uninstall_native_geometry_capture()

        parse_root = output_dir / stem
        search_root = parse_root if parse_root.is_dir() else output_dir

        result = MinerUParseResult(
            pdf_stem=stem,
            output_dir=search_root,
            mineru_version=get_mineru_version(),
            backend=self.config.backend,
            content_list_path=_find_artifact(search_root, stem, "_content_list.json"),
            middle_json_path=_find_artifact(search_root, stem, "_middle.json"),
            content_list_v2_path=_find_artifact(search_root, stem, "_content_list_v2.json"),
            markdown_path=_find_artifact(search_root, stem, ".md"),
            native_table_geometry=native_geometry,
        )

        if result.content_list_path is None:
            alt = _find_artifact(search_root, stem, "_content_list.json")
            result.content_list_path = alt

        if search_root.is_dir():
            for path in sorted(search_root.rglob("*")):
                if path.is_file():
                    rel = str(path.relative_to(search_root))
                    result.raw_artifacts[rel] = str(path)

        logger.info(
            "[MinerU] done — content_list={} middle={} artifacts={} native_geometry={}",
            result.content_list_path,
            result.middle_json_path,
            len(result.raw_artifacts),
            len(result.native_table_geometry),
        )
        return result

    def copy_raw_tree(self, result: MinerUParseResult, dest: Path) -> None:
        if dest.exists():
            shutil.rmtree(dest)
        if result.output_dir.is_dir():
            shutil.copytree(result.output_dir, dest)
