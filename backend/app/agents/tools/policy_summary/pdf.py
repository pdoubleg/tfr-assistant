from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path

from .models import PageText, PdfText, TextChunk

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_pdf_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def doc_id_for_path(path: Path, index: int) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", path.stem).strip("-").lower()
    return f"doc-{index + 1:03d}-{stem[:40] or 'pdf'}"


def extract_pdf_text(path: str | Path, doc_id: str) -> PdfText:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency is installed by backend extras.
        raise RuntimeError("Install pymupdf to extract PDF text.") from exc

    pdf_path = Path(path)
    pages: list[PageText] = []
    with fitz.open(pdf_path) as pdf:
        for page_index in range(len(pdf)):
            page = pdf.load_page(page_index)
            pages.append(
                PageText(
                    doc_id=doc_id,
                    file=pdf_path.name,
                    page=page_index + 1,
                    text=clean_pdf_text(page.get_text("text")),
                )
            )
    return PdfText(doc_id=doc_id, path=pdf_path, file=pdf_path.name, pages=pages)


async def extract_pdf_text_async(path: str | Path, doc_id: str) -> PdfText:
    return await asyncio.to_thread(extract_pdf_text, path, doc_id)


async def extract_many_pdfs(paths: Sequence[str | Path], *, concurrency: int = 4) -> list[PdfText]:
    pdf_paths = [Path(path) for path in paths]
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(index: int, path: Path) -> PdfText:
        async with semaphore:
            return await extract_pdf_text_async(path, doc_id_for_path(path, index))

    return list(
        await asyncio.gather(*(run_one(index, path) for index, path in enumerate(pdf_paths)))
    )


def chunk_pdf_text(
    pdf: PdfText,
    *,
    pages_per_chunk: int = 8,
    overlap_pages: int = 1,
    max_chars_per_chunk: int = 26000,
) -> list[TextChunk]:
    if pages_per_chunk < 1:
        raise ValueError("pages_per_chunk must be >= 1")
    if overlap_pages < 0:
        raise ValueError("overlap_pages must be >= 0")
    if overlap_pages >= pages_per_chunk:
        raise ValueError("overlap_pages must be less than pages_per_chunk")

    chunks: list[TextChunk] = []
    step = pages_per_chunk - overlap_pages
    page_count = len(pdf.pages)
    start = 0
    chunk_no = 1
    while start < page_count:
        end = min(start + pages_per_chunk, page_count)
        selected_pages = pdf.pages[start:end]
        body_parts = [f"\n\n--- PAGE {page.page} ---\n{page.text}" for page in selected_pages]
        text = clean_pdf_text("".join(body_parts))
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rsplit("\n", 1)[0]
        chunks.append(
            TextChunk(
                chunk_id=f"{pdf.doc_id}-chunk-{chunk_no:03d}",
                doc_id=pdf.doc_id,
                file=pdf.file,
                page_start=selected_pages[0].page if selected_pages else 1,
                page_end=selected_pages[-1].page if selected_pages else 1,
                text=text,
            )
        )
        chunk_no += 1
        start += step
    return chunks


def chunk_many_pdfs(
    pdfs: Sequence[PdfText],
    *,
    pages_per_chunk: int = 8,
    overlap_pages: int = 1,
    max_chars_per_chunk: int = 26000,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for pdf in pdfs:
        chunks.extend(
            chunk_pdf_text(
                pdf,
                pages_per_chunk=pages_per_chunk,
                overlap_pages=overlap_pages,
                max_chars_per_chunk=max_chars_per_chunk,
            )
        )
    return chunks
