"""Resolve PDF input from a file path or pycognaize Document."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pycognaize.document import Document


PDF_CANDIDATE_NAMES = (
    "document.pdf",
    "source.pdf",
    "original.pdf",
    "{name}.pdf",
)


def resolve_pdf_path(
    *,
    pdf_path: Optional[Path] = None,
    document: Optional["Document"] = None,
) -> Path:
    """Return a local PDF path for MinerU parsing."""
    if pdf_path is not None:
        path = Path(pdf_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"PDF not found: {path}")
        return path

    env_path = os.environ.get("PDF_PATH") or os.environ.get("DOCUMENT_PDF_PATH")
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if path.is_file():
            return path

    if document is not None:
        found = _find_pdf_under_document(document)
        if found is not None:
            return found

        built = _build_pdf_from_pages(document)
        if built is not None:
            return built

    raise FileNotFoundError(
        "No PDF available. Provide pdf_path, set PDF_PATH, or ensure the "
        "Document storage contains a PDF."
    )


def _find_pdf_under_document(document: "Document") -> Optional[Path]:
    doc_path = getattr(document, "path", None)
    if not doc_path:
        return None

    root = Path(str(doc_path))
    if root.is_file() and root.suffix.lower() == ".pdf":
        return root.resolve()

    if not root.is_dir():
        return None

    doc_name = ""
    metadata = getattr(document, "metadata", {}) or {}
    doc_name = str(metadata.get("documentName") or metadata.get("name") or "")

    candidates: list[Path] = []
    for pattern in PDF_CANDIDATE_NAMES:
        name = pattern.format(name=Path(doc_name).stem if doc_name else "document")
        candidates.append(root / name)
    candidates.extend(sorted(root.glob("*.pdf")))
    candidates.extend(sorted(root.rglob("*.pdf")))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            logger.info("[DOC] using PDF from document storage: {}", resolved)
            return resolved
    return None


def _build_pdf_from_pages(document: "Document") -> Optional[Path]:
    """Fallback: assemble page JPEGs into a temporary PDF for MinerU."""
    try:
        document.load_page_images()
    except Exception as exc:
        logger.warning("[DOC] could not load page images: {}", exc)
        return None

    pages = getattr(document, "pages", None)
    if not pages:
        return None

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.warning("[DOC] reportlab not installed — cannot build PDF from pages")
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    c = canvas.Canvas(str(tmp_path), pagesize=letter)
    width, height = letter

    for page_n in sorted(pages.keys()):
        page = pages[page_n]
        image_arr = getattr(page, "image_arr", None)
        if image_arr is None:
            continue
        img_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img_path.close()
        try:
            from PIL import Image

            Image.fromarray(image_arr).save(img_path.name)
            c.drawImage(img_path.name, 0, 0, width=width, height=height)
            c.showPage()
        finally:
            Path(img_path.name).unlink(missing_ok=True)

    c.save()
    logger.info("[DOC] built temporary PDF from {} page(s): {}", len(pages), tmp_path)
    return tmp_path
