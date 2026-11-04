"""
retrieval.py — pgvector similarity search + sparse FTS search + RRF fusion + BGE reranking + RAG generation
(LUMINA-9, LUMINA-10, LUMINA-11).

Native pgvector similarity search on the `chunks.embedding` column (dense),
PostgreSQL FTS on the `chunks.search_vector` column (sparse), Reciprocal Rank
Fusion (RRF k=60) to merge top 20 candidates, and BGE Reranker v2 M3 to produce
the top 7 chunks for the LLM context.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import transaction
from django.db.models import Q

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from core.models import Answer, Chunk, Document as DocumentModel, History, Query
from . import config
from .reranker import rerank_chunks
from .services import get_embeddings

logger = logging.getLogger(__name__)


class RagPipelineError(Exception):
    """Kesalahan yang terjadi di dalam pipeline RAG.

    `user_message` adalah pesan Bahasa Indonesia yang aman ditampilkan ke user,
    sedangkan detail teknis tetap dicatat lewat logger (English).
    """

    def __init__(self, user_message: str, http_status: int = 500):
        super().__init__(user_message)
        self.user_message = user_message
        self.http_status = http_status


def _similarity_search(
    question_vector: list[float], top_k: int, user_id: int | None = None
) -> list[Chunk]:
    """
    Native pgvector similarity search (cosine distance) over chunks.embedding.
    Returns the top-k Chunk objects ordered by similarity.

    Metadata filtering WAJIB (kontrol keamanan):
    - Chunk dibatasi ke dokumen milik user yang bertanya ATAU dokumen yang
      diunggah oleh admin/staff (diperlakukan sebagai knowledge base bersama).
    - Hanya dokumen dengan status `indexed` yang dipertimbangkan.
    """
    from pgvector.django import CosineDistance

    qs = Chunk.objects.filter(embedding__isnull=False, deleted_at__isnull=True).select_related("document")
    if user_id is not None:
        qs = qs.filter(
            Q(document__user_id=user_id) | Q(document__user__is_staff=True)
        )
    qs = (
        qs.filter(document__status=DocumentModel.Status.INDEXED, document__deleted_at__isnull=True)
        .annotate(distance=CosineDistance("embedding", question_vector))
        .order_by("distance")[:top_k]
    )
    return list(qs)


def _expand_visual_pairs(chunks: list[Chunk], user_id: int) -> list[Chunk]:
    """Include the OCR/Vision counterpart for a retrieved image, within user scope."""
    expanded = list(chunks)
    seen_ids = {chunk.id for chunk in chunks}
    seen_pairs: set[tuple[int, str, str]] = set()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        source_type = metadata.get("source_type")
        image_ref = metadata.get("image_ref")
        if source_type not in {"ocr", "vision"} or not isinstance(image_ref, str):
            continue
        counterpart = "vision" if source_type == "ocr" else "ocr"
        pair = (chunk.document_id, image_ref, counterpart)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        siblings = Chunk.objects.filter(
            document_id=chunk.document_id,
            document__status=DocumentModel.Status.INDEXED,
            document__deleted_at__isnull=True,
            metadata__image_ref=image_ref,
            metadata__source_type=counterpart,
            deleted_at__isnull=True,
        ).filter(
            Q(document__user_id=user_id) | Q(document__user__is_staff=True)
        ).select_related("document")[:2]
        for sibling in siblings:
            if sibling.id not in seen_ids:
                expanded.append(sibling)
                seen_ids.add(sibling.id)
    return expanded
def _sparse_search(
    query_text: str,
    top_k: int,
    user_id: int | None = None,
    document_ids: list[int] | None = None,
) -> list[Chunk]:
    """
    PostgreSQL Full-Text Search (sparse retrieval) over chunks.search_vector.
    Returns the top-k Chunk objects ordered by ts_rank relevance score.

    Metadata filtering WAJIB (kontrol keamanan):
    - Chunk dibatasi ke dokumen milik user yang bertanya ATAU dokumen yang
      diunggah oleh admin/staff (diperlakukan sebagai knowledge base bersama).
    - Hanya dokumen dengan status `indexed` yang dipertimbangkan.
    - Chunk yang sudah soft-deleted diabaikan.
    """
    # plainto_tsquery joins every term with AND, which frequently returns zero
    # rows for natural-language questions. Use OR across normalized lexemes and
    # let ts_rank reward chunks that match more of the question terms.
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query_text.casefold())))
    if not terms:
        return []
    search_query = SearchQuery(
        " | ".join(terms),
        config="pg_catalog.simple",
        search_type="raw",
    )

    qs = (
        Chunk.objects
        .filter(search_vector__isnull=False, deleted_at__isnull=True)
        .select_related("document")
    )
    if user_id is not None:
        qs = qs.filter(
            Q(document__user_id=user_id) | Q(document__user__is_staff=True)
        )
    if document_ids is not None:
        qs = qs.filter(document_id__in=document_ids)
    qs = (
        qs.filter(
            document__status=DocumentModel.Status.INDEXED,
            document__deleted_at__isnull=True,
            search_vector=search_query,
        )
        .annotate(rank=SearchRank("search_vector", search_query))
        .order_by("-rank", "id")[:top_k]
    )
    return list(qs)


def _rrf_fusion(
    dense_results: list[Chunk],
    sparse_results: list[Chunk],
    k: int = config.RRF_K,
    top_k: int = config.TOP_K,
) -> list[Chunk]:
    """
    Reciprocal Rank Fusion (RRF) untuk menggabungkan hasil Dense (pgvector) dan Sparse (PostgreSQL FTS).
    Formula: RRF_Score(d) = sum(1 / (k + rank_i(d)))

    Setiap chunk yang dikembalikan akan memiliki atribut `rrf_score` yang menyimpan nilai RRF score.
    """
    scores: dict[int, float] = {}
    chunk_map: dict[int, Chunk] = {}

    for rank, chunk in enumerate(dense_results, start=1):
        chunk_map[chunk.id] = chunk
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (1.0 / (k + rank))

    for rank, chunk in enumerate(sparse_results, start=1):
        chunk_map[chunk.id] = chunk
        scores[chunk.id] = scores.get(chunk.id, 0.0) + (1.0 / (k + rank))

    sorted_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    top_chunks = []
    for cid in sorted_chunk_ids[:top_k]:
        chunk = chunk_map[cid]
        chunk.rrf_score = scores[cid]
        top_chunks.append(chunk)

    return top_chunks

def _format_context(chunks: list[Chunk]) -> str:
    """Format retrieved chunks into the context block for the LLM prompt."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.document.document_name
        page = chunk.page
        loc = source + (f", hal. {int(page)}" if page is not None else "")
        metadata = chunk.metadata or {}
        if page is None and metadata.get("section") is not None:
            loc += f", bagian {int(metadata['section']) + 1}"
        origin = {
            "document_text": "teks dokumen",
            "ocr": "OCR",
            "vision": "Gemini Vision",
        }.get(metadata.get("source_type"), "asal belum tercatat")
        if metadata.get("image_ref"):
            origin += f", gambar {metadata['image_ref']}"
        if metadata.get("source_type") == "ocr" and metadata.get("ocr_confidence") is not None:
            origin += f", keyakinan OCR {metadata['ocr_confidence']:.2f}"
        header = f"[Excerpt {i} — {loc}; asal: {origin}]"
        parts.append(f"{header}\n{chunk.chunk_text}")
    return "\n\n---\n\n".join(parts)



def _build_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=config.GEMINI_TEMPERATURE,
        max_output_tokens=config.GEMINI_MAX_TOKENS,
        streaming=False,
    )


def _is_transient_llm_error(exc: BaseException) -> bool:
    """Return True for connection failures and retryable upstream responses."""
    transient_error_names = {
        "ConnectError",
        "ConnectTimeout",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
    }
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if current.__class__.__name__ in transient_error_names:
            return True

        status_code = getattr(current, "status_code", None)
        try:
            if status_code is not None and int(status_code) >= 500:
                return True
        except (TypeError, ValueError):
            pass

        current = current.__cause__ or current.__context__
    return False


def _invoke_llm_with_retry(chain: Any, payload: dict[str, str]) -> str:
    """Invoke Gemini and retry once for transient transport failures."""
    for attempt in range(1, config.GEMINI_MAX_ATTEMPTS + 1):
        try:
            return chain.invoke(payload)
        except Exception as exc:
            if (
                attempt >= config.GEMINI_MAX_ATTEMPTS
                or not _is_transient_llm_error(exc)
            ):
                raise
            logger.warning(
                "Transient LLM error on attempt %s/%s; retrying in %.1fs: %s",
                attempt,
                config.GEMINI_MAX_ATTEMPTS,
                config.GEMINI_RETRY_DELAY_SECONDS,
                exc,
            )
            time.sleep(config.GEMINI_RETRY_DELAY_SECONDS)

    raise RuntimeError("LLM invocation exhausted without a result")


def _save_answer(query: Query, answer_text: str, sources: list[dict]) -> int:
    """Persist the answer and link it to the query via History."""
    with transaction.atomic():
        answer = Answer.objects.create(
            query=query,
            answer_text=answer_text,
            sources=sources,
        )
        History.objects.create(
            user=query.user,
            query=query,
            answer=answer,
        )
    return answer.id


def run_rag_query(query_id: int, question: str, top_k: int | None = None) -> dict[str, Any]:
    """
    Run the full RAG pipeline for a user question:
    embed question → hybrid search (dense + sparse) → RRF fusion (top 20) →
    BGE Reranker v2 M3 (top 7) → build context → Gemini → save.

    Returns a dict with answer, sources, response_time_ms, and answer_id.
    Raises RagPipelineError dengan pesan Bahasa Indonesia bila pipeline gagal.
    """
    top_k = top_k or config.TOP_K
    dense_top_k = config.DENSE_TOP_K
    sparse_top_k = config.SPARSE_TOP_K
    reranker_input_k = config.RERANKER_INPUT_K
    rrf_k = config.RRF_K

    try:
        query = Query.objects.get(pk=query_id)
    except Query.DoesNotExist:
        raise RagPipelineError("Pertanyaan tidak ditemukan.", http_status=404)

    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set")
        raise RagPipelineError(
            "Server belum dikonfigurasi untuk menghasilkan jawaban "
            "(API key LLM belum tersedia). Hubungi administrator.",
            http_status=503,
        )

    start = time.time()

    # 1. Embed the question with E5 query prefix
    query.current_step = "embedding"
    query.save(update_fields=["current_step", "updated_at"])
    embeddings = get_embeddings()
    question_vector = embeddings.embed_query(f"query: {question}")

    # 2. Hybrid search (Dense pgvector + Sparse PostgreSQL FTS) + RRF Fusion (Top 20 candidates)
    query.current_step = "similarity_search"
    query.save(update_fields=["current_step", "updated_at"])
    dense_chunks = _similarity_search(question_vector, dense_top_k, user_id=query.user_id)
    sparse_chunks = _sparse_search(question, sparse_top_k, user_id=query.user_id)
    candidate_chunks = _rrf_fusion(dense_chunks, sparse_chunks, k=rrf_k, top_k=reranker_input_k)

    if not candidate_chunks:
        raise RagPipelineError(
            "Belum ada dokumen terindeks yang bisa dijadikan sumber jawaban. "
            "Silakan unggah dokumen terlebih dahulu atau tunggu proses "
            "pengindeksan selesai.",
            http_status=409,
        )

    # 3. Rerank candidate chunks with BGE Reranker v2 M3 (Top 20 -> Top 7)
    query.current_step = "reranking"
    query.save(update_fields=["current_step", "updated_at"])
    chunks, rerank_ms, fallback_used = rerank_chunks(
        query=question,
        chunks=candidate_chunks,
        top_k=top_k,
    )
    logger.info(
        "Reranking completed for query %s: %d chunks selected in %.2f ms (fallback: %s)",
        query_id,
        len(chunks),
        rerank_ms,
        fallback_used,
    )

    chunks = _expand_visual_pairs(chunks, user_id=query.user_id)

    # 4. Build context
    query.current_step = "context"
    query.save(update_fields=["current_step", "updated_at"])
    context = _format_context(chunks)

    # 5. Generate answer with Gemini
    query.current_step = "generate"
    query.save(update_fields=["current_step", "updated_at"])

    llm = _build_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", config.RAG_SYSTEM_PROMPT),
        ("human", "{question}"),
    ])
    chain = prompt | llm | StrOutputParser()
    try:
        answer_text = _invoke_llm_with_retry(
            chain,
            {"context": context, "question": question},
        )
    except Exception as exc:
        logger.exception("LLM generation failed")
        raise RagPipelineError(
            "Gagal menghasilkan jawaban saat ini. Silakan coba beberapa saat lagi.",
            http_status=502,
        ) from exc

    if not (answer_text or "").strip():
        logger.warning("LLM returned an empty answer for query %s", query_id)
        raise RagPipelineError(
            "Jawaban tidak dapat dibuat untuk pertanyaan ini. "
            "Silakan coba ulangi pertanyaan Anda.",
            http_status=502,
        )

    elapsed = round((time.time() - start) * 1000)

    # 6. Build sources from the retrieved chunks
    sources = [
        {
            "source": chunk.document.document_name,
            "page": chunk.page,
            "score": round(float(chunk.rerank_score), 6) if hasattr(chunk, "rerank_score") else (
                round(float(chunk.rrf_score), 6) if hasattr(chunk, "rrf_score") else (
                    round(float(1.0 - chunk.distance), 4) if hasattr(chunk, "distance") else None
                )
            ),
            "excerpt": chunk.chunk_text[:200],
            "source_type": (chunk.metadata or {}).get("source_type"),
            "image_ref": (chunk.metadata or {}).get("image_ref"),
            "ocr_confidence": (chunk.metadata or {}).get("ocr_confidence"),
        }
        for chunk in chunks
    ]

    # 7. Persist answer + history, update query status
    answer_id = _save_answer(query, answer_text, sources)
    query.status = Query.Status.ANSWERED
    query.response_time_ms = elapsed
    query.current_step = "done"
    query.save(update_fields=["status", "response_time_ms", "current_step", "updated_at"])

    return {
        "success": True,
        "query_id": query_id,
        "answer_id": answer_id,
        "answer": answer_text,
        "response_time_ms": elapsed,
        "sources": sources,
    }
