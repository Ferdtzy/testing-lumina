"""
ocr_service.py — PaddleOCR integration untuk Lumina AI.
Mengkonversi gambar/PDF ke teks menggunakan PaddleOCR.
"""

from __future__ import annotations

import logging
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any

from ingest import config

logger = logging.getLogger(__name__)

# Must be set BEFORE any paddle/paddlex import to avoid oneDNN crash on Windows
os.environ["PADDLE_DISABLE_ONE_DNN"] = "1"
os.environ["FLAGS_default_is_paddle_enabled"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

_ocr_engine: Any | None = None


def get_ocr_engine() -> Any:
    """Inisialisasi PaddleOCR (singleton)."""
    global _ocr_engine
    if _ocr_engine is None:
        logger.info("Initializing PaddleOCR (lang=%s)", config.OCR_LANG)
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(
            lang=config.OCR_LANG,
            device=config.OCR_DEVICE,
            cpu_threads=config.OCR_CPU_THREADS,
            enable_mkldnn=False,
            text_det_limit_side_len=config.OCR_DET_MAX_SIDE,
            text_det_limit_type='max',
            text_recognition_batch_size=config.OCR_REC_BATCH_SIZE,
            textline_orientation_batch_size=config.OCR_REC_BATCH_SIZE,
            use_doc_orientation_classify=config.OCR_USE_DOC_ORIENTATION,
            use_doc_unwarping=config.OCR_USE_DOC_UNWARPING,
            use_textline_orientation=config.OCR_USE_TEXTLINE_ORIENTATION,
        )
    return _ocr_engine


def _parse_ocr_result(result: Any) -> list[dict]:
    """Parse PaddleOCR 3.7.0 OCRResult into uniform dict list."""
    extracted = []
    if not result:
        return extracted

    # PaddleOCR 3.7.0: result[0] is an OCRResult (dict-like)
    # Keys: rec_texts, rec_scores, rec_polys
    ocr_result = result[0]
    texts = ocr_result.get("rec_texts", [])
    scores = ocr_result.get("rec_scores", [])
    polys = ocr_result.get("rec_polys", [])

    for i, (text, score) in enumerate(zip(texts, scores)):
        bbox = polys[i].tolist() if i < len(polys) else []
        extracted.append({
            "text": str(text),
            "confidence": float(score),
            "bbox": bbox,
        })
    return extracted


def ocr_image(file_path: Path) -> list[dict]:
    """
    Jalankan OCR pada satu gambar.

    Returns:
        list of dict: [{"text": ..., "confidence": ..., "bbox": ...}, ...]
    """
    engine = get_ocr_engine()
    result = engine.predict(str(file_path))

    extracted = _parse_ocr_result(result)

    logger.info("OCR: %d text blocks extracted from %s",
                len(extracted), file_path.name)
    return extracted


def _poppler_path() -> str | None:
    """Return bundled Poppler only on Windows; Linux resolves it from PATH."""
    if os.name != "nt":
        return None
    configured_path = Path(config.POPPLER_PATH)
    return str(configured_path) if configured_path.is_dir() else None


def _analyze_pdf_image_regions(
    page: Any,
    page_number: int,
    temp_dir: Path,
    surrounding_text: str,
) -> list[dict]:
    """Analyze significant embedded raster images instead of the full PDF page."""
    from ingest.vision_service import analyze_image

    regions: list[dict] = []
    seen_images: set[bytes] = set()
    max_images = max(0, config.VISION_PDF_MAX_IMAGES_PER_PAGE)
    try:
        images = page.images
        for image_index, image_file in enumerate(images, start=1):
            if len(regions) >= max_images or image_index > max_images * 4:
                break
            try:
                image = image_file.image
                if (
                    image is None
                    or image.width * image.height < config.VISION_PDF_MIN_IMAGE_PIXELS
                ):
                    continue
                digest = sha256(image_file.data).digest()
                if digest in seen_images:
                    continue
                seen_images.add(digest)
                image_ref = f"page-{page_number}-image-{image_index}"
                image_path = temp_dir / f"{image_ref}.png"
                image.save(image_path, format="PNG")
                try:
                    blocks = ocr_image(image_path)
                except Exception:
                    logger.exception("OCR failed for PDF image %s", image_ref)
                    blocks = []
                region_text = " ".join(block["text"] for block in blocks)
                scores = [
                    float(block["confidence"])
                    for block in blocks if block.get("confidence") is not None
                ]
                analysis = analyze_image(image_path, region_text, surrounding_text)
                if region_text or analysis:
                    regions.append({
                        "image_ref": image_ref,
                        "text": region_text,
                        "confidence": round(sum(scores) / len(scores), 4) if scores else None,
                        "visual_analysis": analysis.model_dump() if analysis else None,
                    })
            except Exception:
                logger.exception(
                    "PDF image %s on page %s could not be analyzed",
                    image_index, page_number,
                )
    except Exception:
        logger.exception("Could not extract PDF images on page %s", page_number)
    return regions


def ocr_pdf_pages(
    file_path: Path,
    page_numbers: list[int] | None = None,
    analyze_visuals: bool = False,
    page_contexts: dict[int, str] | None = None,
) -> list[dict]:
    """
    Jalankan OCR pada halaman PDF tertentu.

    ``page_numbers`` memakai nomor halaman berbasis nol agar konsisten dengan
    metadata PyPDFLoader. Jika kosong, semua halaman akan diproses.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "pdf2image diperlukan untuk OCR PDF. "
            "Install: pip install pdf2image poppler-utils"
        )

    if page_numbers is None:
        from pypdf import PdfReader

        page_numbers = list(range(len(PdfReader(str(file_path)).pages)))

    all_results: list[dict] = []
    pdf_reader = None
    if analyze_visuals and config.VISION_ENABLED and config.GEMINI_API_KEY:
        from pypdf import PdfReader

        try:
            pdf_reader = PdfReader(str(file_path))
        except Exception:
            logger.exception("Could not inspect PDF images in %s; using full-page Vision", file_path.name)
    with tempfile.TemporaryDirectory(prefix="lumina-ocr-") as temp_dir:
        for page_index in sorted(set(page_numbers)):
            images = convert_from_path(
                str(file_path),
                dpi=config.OCR_PDF_DPI,
                first_page=page_index + 1,
                last_page=page_index + 1,
                poppler_path=_poppler_path(),
            )
            if not images:
                continue

            temp_path = Path(temp_dir) / f"page-{page_index + 1}.png"
            images[0].save(temp_path)
            page_texts = ocr_image(temp_path)
            ocr_text = " ".join(t["text"] for t in page_texts)
            scores = [
                float(block["confidence"])
                for block in page_texts if block.get("confidence") is not None
            ]
            visual_analysis = None
            visual_regions: list[dict] = []
            if analyze_visuals:
                from ingest.vision_service import analyze_image

                if pdf_reader is not None and page_index < len(pdf_reader.pages):
                    visual_regions = _analyze_pdf_image_regions(
                        pdf_reader.pages[page_index], page_index + 1,
                        Path(temp_dir), (page_contexts or {}).get(page_index, ""),
                    )
                # Scanned pages and vector drawings may have no separate raster region.
                if not any(region["visual_analysis"] for region in visual_regions):
                    analysis = analyze_image(
                        temp_path, ocr_text, (page_contexts or {}).get(page_index, ""),
                    )
                    visual_analysis = analysis.model_dump() if analysis else None
            all_results.append({
                "page_num": page_index + 1,
                "text": ocr_text,
                "blocks": len(page_texts),
                "confidence": round(sum(scores) / len(scores), 4) if scores else None,
                "visual_analysis": visual_analysis,
                "visual_regions": visual_regions,
            })

    logger.info("OCR PDF: %d pages processed from %s",
                len(all_results), file_path.name)
    return all_results


def ocr_pdf(file_path: Path) -> list[dict]:
    """Jalankan OCR pada seluruh halaman PDF."""
    return ocr_pdf_pages(file_path)


def ocr_document(file_path: Path) -> dict:
    """
    Entry point OCR — deteksi tipe file dan jalankan OCR yang tepat.

    Returns:
        dict: {"text": ..., "pages": ..., "raw_results": ...}
    """
    suffix = file_path.suffix.lower()
    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

    if suffix in image_ext:
        results = ocr_image(file_path)
        text = " ".join(r["text"] for r in results)
        return {"text": text, "pages": 1, "raw_results": results}

    elif suffix == ".pdf":
        results = ocr_pdf(file_path)
        text = " ".join(r["text"] for r in results)
        return {"text": text, "pages": len(results), "raw_results": results}

    else:
        raise ValueError(f"Format tidak didukung untuk OCR: {suffix}")
