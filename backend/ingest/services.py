"""
services.py — Django port of the RAG ingest pipeline (ai/ingest.py + ai/flask_api.py).

Pipeline: load → preprocess → chunk → embed → persist (pgvector).
Uses Django ORM + pgvector instead of raw MySQL + FAISS.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.utils import timezone

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
)
from langchain_huggingface import HuggingFaceEmbeddings

from core.models import Document as DocumentModel, Chunk, IngestLog
from . import config
from ingest.ocr_service import ocr_document

logger = logging.getLogger(__name__)

# ── Embedding model (lazy-loaded singleton) ────────────────────────────────────
_embeddings: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the HuggingFace embedding model once and cache it."""
    global _embeddings
    if _embeddings is None:
        logger.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
        cache_folder = str(config.EMBEDDING_MODEL_CACHE_DIR) if config.EMBEDDING_MODEL_CACHE_DIR else None
        _embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            cache_folder=cache_folder,
            model_kwargs={"device": config.EMBEDDING_DEVICE},
            encode_kwargs={"normalize_embeddings": True, "batch_size": config.EMBEDDING_BATCH_SIZE},
        )
    return _embeddings


# ── Logging helpers ────────────────────────────────────────────────────────────

def _log_ingest(
    document_id: int | None,
    step: str,
    message: str,
    session_id: str | None = None,
    status: str = "started",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert an ingest log row."""
    if document_id is None:
        return
    valid_session_id = None
    if session_id:
        if isinstance(session_id, uuid.UUID):
            valid_session_id = session_id
        else:
            try:
                valid_session_id = uuid.UUID(str(session_id))
            except (ValueError, AttributeError):
                valid_session_id = None

    try:
        IngestLog.objects.create(
            document_id=document_id,
            session_id=valid_session_id,
            step=step,
            status=status,
            message=message,
            error_message=error_message,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to insert ingest log: %s", exc)


def _mark_failed(document_id: int | None, session_id: str | None, error_message: str) -> None:
    """Uniform failure path: logs an 'error' step and flips status to failed."""
    if document_id is None:
        return

    try:
        document = DocumentModel.objects.filter(pk=document_id).first()
        if (
            document is not None
            and document.status == DocumentModel.Status.INDEXED
            and document.chunks.filter(deleted_at__isnull=True).exists()
        ):
            _log_ingest(
                document_id,
                "skip",
                "Ignored failure from duplicate task because document is already indexed.",
                session_id,
                status="success",
                metadata={"ignored_error": error_message},
            )
            return
    except Exception:  # noqa: BLE001
        pass

    _log_ingest(
        document_id,
        "error",
        "Pipeline ingest gagal.",
        session_id,
        status="failed",
        error_message=error_message,
    )
    try:
        DocumentModel.objects.filter(pk=document_id).exclude(
            status=DocumentModel.Status.INDEXED,
        ).update(
            status=DocumentModel.Status.FAILED,
            updated_at=timezone.now(),
        )
    except Exception:  # noqa: BLE001
        pass


# ── Step functions ─────────────────────────────────────────────────────────────

def _copy_to_documents(file_path: Path, original_filename: str, document_id: int | None, session_id: str | None) -> Path:
    """Copy the uploaded file into the documents directory with UUID name."""
    safe_name = file_path.name
    dest = config.DOCUMENTS_DIR / safe_name
    if dest.resolve() != file_path.resolve():
        shutil.copy2(file_path, dest)
        _log_ingest(document_id, "copy", f"Copied to documents/{dest.name} (original: {original_filename})", session_id)
    else:
        _log_ingest(document_id, "copy", f"Already in documents/{file_path.name}", session_id)
    return dest


def _ocr_confidence(blocks: list[dict[str, Any]]) -> float | None:
    """Mean PaddleOCR recognition score, or None when scores are unavailable."""
    scores = [float(block["confidence"]) for block in blocks if block.get("confidence") is not None]
    return round(sum(scores) / len(scores), 4) if scores else None


def _load_document(file_path: Path, document_id: int | None, session_id: str | None, is_ocr: bool = False) -> list[Document]:
    """Load a PDF/DOCX/TXT/image file into LangChain Documents.
    Image files use OCR via PaddleOCR when is_ocr=True."""
    suffix = file_path.suffix.lower()
    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

    if is_ocr or suffix in image_ext:
        from ingest.ocr_service import ocr_document
        from ingest.vision_service import analyze_image, format_visual_analysis
        try:
            result = ocr_document(file_path)
            visual_text = format_visual_analysis(analyze_image(file_path, result["text"]))
        except Exception as exc:
            logger.error("OCR failed for %s: %s", file_path.name, exc)
            raise ValueError(f"OCR gagal untuk {file_path.name}: {exc}")
        _log_ingest(document_id, "ocr", f"OCR extracted {len(result['text'])} chars from {file_path.name}", session_id)
        base_metadata = {"source_file": file_path.name, "page": 0, "image_ref": file_path.name, "ocr_used": True}
        documents = []
        if result["text"].strip():
            documents.append(Document(
                page_content=result["text"],
                metadata={**base_metadata, "source_type": "ocr", "ocr_confidence": _ocr_confidence(result["raw_results"])},
            ))
        if visual_text:
            documents.append(Document(
                page_content=visual_text,
                metadata={**base_metadata, "source_type": "vision"},
            ))
        return documents

    if suffix == ".pdf":
        return _load_pdf_hybrid(file_path, document_id, session_id)
    elif suffix == ".docx":
        return _load_docx_hybrid(file_path, document_id, session_id)
    elif suffix == ".txt":
        try:
            docs = TextLoader(str(file_path), encoding="utf-8").load()
        except Exception:  # noqa: BLE001
            docs = TextLoader(str(file_path), encoding="latin-1").load()
    else:
        raise ValueError(f"Unsupported extension '{suffix}'.")

    total_chars = sum(len(doc.page_content) for doc in docs)
    page_count = len(docs)

    if page_count > 500:
        raise ValueError(f"Dokumen melebihi batas maksimal 500 halaman (ditemukan: {page_count})")

    if total_chars > 2_000_000:
        raise ValueError(f"Total karakter melebihi batas maksimal 2 juta (ditemukan: {total_chars})")

    for doc in docs:
        doc.metadata.setdefault("source_file", file_path.name)
        doc.metadata.setdefault("source_type", "document_text")

    _log_ingest(document_id, "load", f"Loaded {page_count} page(s)/section(s), {total_chars:,} chars", session_id)
    return docs


def _select_docx_vision_relationships(document_part: Any) -> set[str]:
    """Select the largest unique DOCX images for Gemini Vision enrichment."""
    from PIL import Image

    max_images = max(0, config.VISION_DOCX_MAX_IMAGES)
    if max_images == 0:
        return set()

    supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    candidates: list[tuple[int, str]] = []
    seen_hashes: set[bytes] = set()
    for relationship_id, image_part in document_part.related_parts.items():
        suffix = Path(str(image_part.partname)).suffix.lower()
        if suffix not in supported_extensions:
            continue
        blob = image_part.blob
        fingerprint = hashlib.sha256(blob).digest()
        if fingerprint in seen_hashes:
            continue
        seen_hashes.add(fingerprint)
        try:
            with Image.open(BytesIO(blob)) as image:
                pixel_count = image.width * image.height
        except Exception:  # noqa: BLE001 - malformed image is skipped by Vision
            logger.warning("Skipping unreadable DOCX image for Vision: %s", image_part.partname)
            continue
        if pixel_count >= config.VISION_DOCX_MIN_IMAGE_PIXELS:
            candidates.append((pixel_count, relationship_id))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return {relationship_id for _, relationship_id in candidates[:max_images]}


def _ocr_docx_images(
    element: Any,
    document_part: Any,
    temp_dir: Path,
    surrounding_text: str = "",
    section_index: int = 0,
    source_file: str = "",
    vision_relationship_ids: set[str] | None = None,
) -> list[Document]:
    """Extract OCR and visual descriptions as separate source documents."""
    from docx.oxml.ns import qn
    from ingest.ocr_service import ocr_image
    from ingest.vision_service import analyze_image, format_visual_analysis

    supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    results: list[Document] = []
    for image_number, blip in enumerate(element.xpath(".//a:blip"), start=1):
        relationship_id = blip.get(qn("r:embed"))
        image_part = document_part.related_parts.get(relationship_id)
        if image_part is None:
            continue

        suffix = Path(str(image_part.partname)).suffix.lower()
        if suffix not in supported_extensions:
            logger.info("Skipping unsupported DOCX image format: %s", suffix)
            continue

        image_path = temp_dir / f"image-{image_number}{suffix}"
        image_path.write_bytes(image_part.blob)
        blocks = ocr_image(image_path)
        ocr_text = " ".join(block["text"] for block in blocks).strip()
        visual_text = ""
        if vision_relationship_ids is None or relationship_id in vision_relationship_ids:
            visual_text = format_visual_analysis(
                analyze_image(image_path, ocr_text, surrounding_text)
            )
        metadata = {
            "source_file": source_file,
            "section": section_index,
            "image_ref": f"section-{section_index}-image-{image_number}",
            "ocr_used": True,
        }
        if ocr_text:
            results.append(Document(
                page_content=ocr_text,
                metadata={**metadata, "source_type": "ocr", "ocr_confidence": _ocr_confidence(blocks)},
            ))
        if visual_text:
            results.append(Document(
                page_content=visual_text,
                metadata={**metadata, "source_type": "vision"},
            ))
    return results


def _load_docx_hybrid(
    file_path: Path,
    document_id: int | None,
    session_id: str | None,
) -> list[Document]:
    """Read DOCX text and keep OCR/Vision image content as distinct sources."""
    from docx import Document as WordDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    word_document = WordDocument(str(file_path))
    sections: list[Document] = []
    image_count = 0
    vision_relationship_ids = _select_docx_vision_relationships(word_document.part)

    with tempfile.TemporaryDirectory(prefix="lumina-docx-ocr-") as temp_name:
        temp_dir = Path(temp_name)
        for section_index, element in enumerate(word_document.element.body.iterchildren()):
            if element.tag.endswith("}p"):
                extracted_text = Paragraph(element, word_document).text.strip()
            elif element.tag.endswith("}tbl"):
                table = Table(element, word_document)
                extracted_text = "\n".join(
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in table.rows
                ).strip()
            else:
                continue

            try:
                image_texts = _ocr_docx_images(
                    element,
                    word_document.part,
                    temp_dir,
                    extracted_text,
                    section_index,
                    file_path.name,
                    vision_relationship_ids,
                )
            except Exception as exc:
                logger.error("DOCX image OCR failed for %s: %s", file_path.name, exc)
                raise ValueError(f"OCR gambar DOCX gagal untuk {file_path.name}: {exc}") from exc

            image_count += len({doc.metadata["image_ref"] for doc in image_texts})
            if extracted_text:
                sections.append(Document(
                    page_content=extracted_text,
                    metadata={
                        "source_file": file_path.name,
                        "section": section_index,
                        "source_type": "document_text",
                    },
                ))
            sections.extend(image_texts)

    _log_ingest(
        document_id,
        "ocr" if image_count else "load",
        f"Loaded {len(sections)} DOCX section(s); OCR extracted text from "
        f"{image_count} image(s); Vision selected up to "
        f"{len(vision_relationship_ids)} significant image(s)",
        session_id,
    )
    return sections


def _pdf_pages_requiring_ocr(file_path: Path, docs: list[Document]) -> list[int]:
    """Select scanned pages and pages containing embedded images for OCR."""
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    selected: list[int] = []
    for page_index, page in enumerate(reader.pages):
        extracted_text = docs[page_index].page_content if page_index < len(docs) else ""
        has_little_text = len(extracted_text.strip()) < config.OCR_PDF_MIN_TEXT_CHARS
        try:
            has_images = bool(page.images)
        except Exception:  # noqa: BLE001 - malformed image metadata must not abort ingest
            has_images = False
        if has_little_text or has_images:
            selected.append(page_index)
    return selected


def _merge_pdf_page_text(extracted_text: str, ocr_text: str) -> str:
    """Combine PDF and OCR text while avoiding obvious full-page duplicates."""
    extracted_text = extracted_text.strip()
    ocr_text = ocr_text.strip()
    if not extracted_text:
        return ocr_text
    if not ocr_text:
        return extracted_text

    normalized_extracted = re.sub(r"\W+", "", extracted_text).lower()
    normalized_ocr = re.sub(r"\W+", "", ocr_text).lower()
    if normalized_ocr in normalized_extracted or normalized_extracted in normalized_ocr:
        return extracted_text if len(extracted_text) >= len(ocr_text) else ocr_text
    return f"{extracted_text}\n\n[Teks dari gambar]\n{ocr_text}"


def _load_pdf_hybrid(
    file_path: Path,
    document_id: int | None,
    session_id: str | None,
) -> list[Document]:
    """Extract digital text and OCR scanned/image-bearing PDF pages."""
    docs = PyPDFLoader(str(file_path)).load()
    for page_index, doc in enumerate(docs):
        doc.metadata.setdefault("page", page_index)
        doc.metadata.setdefault("source_file", file_path.name)
        doc.metadata["source_type"] = "document_text"

    selected_pages = _pdf_pages_requiring_ocr(file_path, docs)
    if not selected_pages:
        _log_ingest(document_id, "load", f"Loaded {len(docs)} PDF page(s); OCR not required", session_id)
        return docs

    from ingest.ocr_service import ocr_pdf_pages

    try:
        ocr_results = ocr_pdf_pages(
            file_path,
            selected_pages,
            analyze_visuals=True,
            page_contexts={
                index: docs[index].page_content
                for index in selected_pages if index < len(docs)
            },
        )
    except Exception as exc:
        logger.error("PDF OCR failed for %s: %s", file_path.name, exc)
        raise ValueError(f"OCR PDF gagal untuk {file_path.name}: {exc}") from exc

    from ingest.vision_service import VisualAnalysis, format_visual_analysis

    visual_docs: list[Document] = []
    for result in ocr_results:
        page_index = result["page_num"] - 1
        ocr_text = result["text"].strip()
        if page_index < len(docs) and ocr_text:
            digital_text = docs[page_index].page_content.strip()
            preferred = _merge_pdf_page_text(digital_text, ocr_text)
            if preferred == digital_text:
                ocr_text = ""
            elif preferred == ocr_text:
                docs[page_index].page_content = ""
        metadata = {
            "source_file": file_path.name,
            "page": page_index,
            "image_ref": f"page-{result['page_num']}",
            "ocr_used": True,
        }
        if ocr_text:
            visual_docs.append(Document(
                page_content=ocr_text,
                metadata={**metadata, "source_type": "ocr", "ocr_confidence": result.get("confidence")},
            ))
        visual_data = result.get("visual_analysis")
        visual_text = format_visual_analysis(
            VisualAnalysis.model_validate(visual_data) if visual_data else None
        )
        if visual_text:
            visual_docs.append(Document(
                page_content=visual_text,
                metadata={**metadata, "source_type": "vision"},
            ))
        for region in result.get("visual_regions", []):
            region_metadata = {**metadata, "image_ref": region["image_ref"]}
            if region["text"].strip():
                visual_docs.append(Document(
                    page_content=region["text"],
                    metadata={
                        **region_metadata, "source_type": "ocr",
                        "ocr_confidence": region.get("confidence"),
                    },
                ))
            region_analysis = region.get("visual_analysis")
            region_visual_text = format_visual_analysis(
                VisualAnalysis.model_validate(region_analysis) if region_analysis else None
            )
            if region_visual_text:
                visual_docs.append(Document(
                    page_content=region_visual_text,
                    metadata={**region_metadata, "source_type": "vision"},
                ))

    _log_ingest(
        document_id,
        "ocr",
        f"OCR processed {len(selected_pages)} of {len(docs)} PDF page(s); "
        f"{sum(len(result.get('visual_regions', [])) for result in ocr_results)} image region(s) analyzed",
        session_id,
    )
    return docs + visual_docs


def _preprocess_documents(docs: list[Document], document_id: int | None, session_id: str | None) -> list[Document]:
    """Clean text: collapse excess newlines/whitespace, drop empty pages."""
    def clean(text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    cleaned = [
        Document(page_content=clean(d.page_content), metadata=d.metadata)
        for d in docs
        if len(clean(d.page_content)) > (
            10 if d.metadata.get("source_type") in {"ocr", "vision"} else 50
        )
    ]
    _log_ingest(document_id, "preprocess", f"Cleaned to {len(cleaned)} page(s)", session_id)
    return cleaned


def _chunk_documents(docs: list[Document], document_id: int | None, session_id: str | None) -> list[Document]:
    """Split documents into chunks using RecursiveCharacterTextSplitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
        add_start_index=True,
    )
    chunks = splitter.split_documents(docs)
    _log_ingest(document_id, "chunk", f"Created {len(chunks)} chunks", session_id)
    return chunks


def _embed_and_persist(
    document: DocumentModel,
    file_path: Path,
    chunks: list[Document],
    session_id: str | None,
) -> int:
    """
    Embed all chunks and persist them to the `chunks` table (pgvector).
    Returns the number of chunks saved.
    """
    embeddings = get_embeddings()

    # Embed all chunk texts in one batch with E5 passage prefix
    texts = [f"passage: {chunk.page_content}" for chunk in chunks]
    vectors = embeddings.embed_documents(texts)

    with transaction.atomic():
        # Delete existing chunks for this document (re-ingest)
        Chunk.objects.filter(document=document).delete()

        # Update path_file
        document.path_file = str(file_path)
        document.is_ocr = any(chunk.metadata.get("ocr_used", False) for chunk in chunks)
        document.save(update_fields=["path_file", "is_ocr", "updated_at"])

        # Bulk-create chunks with embeddings and page metadata
        chunk_objs = []
        for chunk, vector in zip(chunks, vectors):
            page = chunk.metadata.get("page")
            provenance = {
                key: chunk.metadata[key]
                for key in ("source_type", "image_ref", "section", "ocr_confidence", "ocr_used", "start_index")
                if key in chunk.metadata
            }
            chunk_objs.append(
                Chunk(
                    document=document,
                    chunk_text=chunk.page_content,
                    page=int(page) + 1 if page is not None else None,
                    metadata=provenance,
                    embedding=vector,
                )
            )
        Chunk.objects.bulk_create(chunk_objs)

        # Ensure search_vector is populated even if DB trigger did not fire
        Chunk.objects.filter(document=document, search_vector__isnull=True).update(
            search_vector=SearchVector("chunk_text", config="pg_catalog.simple")
        )

    _log_ingest(document.id, "database", f"Saved {len(chunk_objs)} chunks to pgvector", session_id)
    return len(chunk_objs)


def _mark_indexed(document_id: int, session_id: str | None) -> None:
    """Mark the document as indexed after all chunks are embedded and saved."""
    DocumentModel.objects.filter(pk=document_id).update(
        status=DocumentModel.Status.INDEXED,
        updated_at=timezone.now(),
    )
    _log_ingest(
        document_id,
        "complete",
        "All chunks stored",
        session_id,
        status="success",
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_ingest_pipeline(
    file_path: Path,
    original_filename: str,
    document_id: int | None = None,
    user_id: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Run the full ingest pipeline: copy → load → preprocess → chunk → embed → persist.

    Returns a dict with `chunks_added`, `document_id`, and `file_path`.
    """
    valid_session_id = None
    if session_id:
        if isinstance(session_id, uuid.UUID):
            valid_session_id = session_id
        else:
            try:
                valid_session_id = uuid.UUID(str(session_id))
            except (ValueError, AttributeError):
                valid_session_id = None

    try:
        # If document_id is not provided, create Document model first
        if document_id is None:
            if user_id is None:
                raise ValueError("user_id is required when document_id is not provided")
            document = DocumentModel.objects.create(
                user_id=user_id,
                document_name=original_filename,
                path_file=str(file_path),
                file_type=file_path.suffix.lstrip(".").lower(),
                size=file_path.stat().st_size if file_path.exists() else 0,
                status=DocumentModel.Status.PROCESSING,
                ingest_session_id=valid_session_id,
            )
            document_id = document.id
        else:
            document = DocumentModel.objects.get(pk=document_id)

            stored_path = Path(document.path_file)
            active_chunks = document.chunks.filter(deleted_at__isnull=True).count()
            if (
                document.status == DocumentModel.Status.INDEXED
                and active_chunks > 0
                and stored_path.exists()
            ):
                _log_ingest(
                    document_id,
                    "skip",
                    "Duplicate ingest task ignored; document is already indexed.",
                    session_id,
                    status="success",
                    metadata={"chunks": active_chunks},
                )
                return {
                    "chunks_added": active_chunks,
                    "document_id": document_id,
                    "file_path": str(stored_path),
                    "skipped": True,
                }

        # 1. Copy file into documents dir
        dest = _copy_to_documents(file_path, original_filename, document_id, session_id)

        # Deteksi apakah perlu OCR (sebelum load, karena _load_document butuh flag ini)
        image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
        is_ocr = dest.suffix.lower() in image_ext

        # 2. Load document
        docs = _load_document(dest, document_id, session_id, is_ocr=is_ocr)

        # 3. Preprocess / clean
        docs = _preprocess_documents(docs, document_id, session_id)

        # 4. Chunk
        chunks = _chunk_documents(docs, document_id, session_id)

        # 5. Embed + persist to pgvector
        chunks_added = _embed_and_persist(document, dest, chunks, session_id)

        # 6. Mark indexed
        _mark_indexed(document_id, session_id)

        # 7. Cleanup uploaded file if it exists and differs from destination
        if file_path.resolve() != dest.resolve() and file_path.exists():
            try:
                file_path.unlink()
                _log_ingest(document_id, "cleanup", f"Removed upload source: {file_path.name}", session_id)
            except Exception as exc:
                logger.warning("Failed to delete upload file %s: %s", file_path, exc)

        return {
            "chunks_added": chunks_added,
            "document_id": document_id,
            "file_path": str(dest),
        }

    except Exception as exc:
        logger.exception("Ingest pipeline failed")
        _mark_failed(document_id, session_id, str(exc))
        raise
