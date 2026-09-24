"""Genie adapter: MinerU document parsing → TableFields."""

from __future__ import annotations

from typing import Optional

from loguru import logger
from pycognaize import Model
from pycognaize.document import Document

from table_recognition_mineru.config import AppConfig
from table_recognition_mineru.pipeline import MinerUPipeline


class MinerUTableModel(Model):
    """Genie model powered entirely by MinerU document understanding."""

    def evaluate(self, *args, **kwargs):
        raise NotImplementedError("Evaluation is not implemented for MinerUTableModel")

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        super().__init__()
        self.config = config or AppConfig.from_yaml()
        self.pipeline = MinerUPipeline(self.config)

    def predict(self, document: Document) -> Document:
        if "table" in document.y:
            document.y["table"] = []

        result = self.pipeline.process_document(document)
        document.y["table"] = result.tables
        logger.info(
            "[GENIE] predict() complete — {} table(s), mineru {:.1f}s",
            len(result.tables),
            result.timing.mineru_seconds,
        )
        return document
