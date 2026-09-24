"""Configuration loading for table-recognition-mineru."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


@dataclass
class MinerUConfig:
    backend: str = "pipeline"
    parse_method: str = "auto"
    lang: str = "en"
    formula_enable: bool = True
    table_enable: bool = True
    start_page_id: int = 0
    end_page_id: Optional[int] = None


@dataclass
class PipelineConfig:
    debug: bool = True
    output_dir: str = "output"
    diagnostics_subdirs: dict[str, str] = field(
        default_factory=lambda: {
            "raw": "raw",
            "parsed": "parsed",
            "tables": "tables",
            "final": "final",
        }
    )


@dataclass
class AppConfig:
    mineru: MinerUConfig
    pipeline: PipelineConfig
    api_host: str = "https://uat-api.cognaize.com"

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "AppConfig":
        cfg_path = path or DEFAULT_CONFIG_PATH
        raw: dict[str, Any] = {}
        if cfg_path.is_file():
            with cfg_path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}

        mineru_raw = raw.get("mineru", {})
        pipe_raw = raw.get("pipeline", {})
        api_raw = raw.get("api", {})

        end_page = mineru_raw.get("end_page_id")
        return cls(
            api_host=api_raw.get("host", "https://uat-api.cognaize.com"),
            mineru=MinerUConfig(
                backend=str(mineru_raw.get("backend", "pipeline")),
                parse_method=str(mineru_raw.get("parse_method", "auto")),
                lang=str(mineru_raw.get("lang", "en")),
                formula_enable=bool(mineru_raw.get("formula_enable", True)),
                table_enable=bool(mineru_raw.get("table_enable", True)),
                start_page_id=int(mineru_raw.get("start_page_id", 0)),
                end_page_id=int(end_page) if end_page is not None else None,
            ),
            pipeline=PipelineConfig(
                debug=bool(pipe_raw.get("debug", True)),
                output_dir=str(pipe_raw.get("output_dir", "output")),
                diagnostics_subdirs=dict(
                    pipe_raw.get(
                        "diagnostics_subdirs",
                        {
                            "raw": "raw",
                            "parsed": "parsed",
                            "tables": "tables",
                            "final": "final",
                        },
                    )
                ),
            ),
        )

    @property
    def output_root(self) -> Path:
        root = Path(self.pipeline.output_dir)
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        return root
