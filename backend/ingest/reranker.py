"""
reranker.py — BGE Reranker v2 M3 integration with latency logging and timeout fallback (LUMINA-11).

Supports cross-encoder ranking using FlagEmbedding or SentenceTransformers CrossEncoder,
with CPU/GPU device selection, configurable timeout with fallback, and execution timing.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any

from core.models import Chunk
from . import config

logger = logging.getLogger(__name__)

# Lazy singleton reranker instance
_reranker_instance: Any = None


def get_reranker() -> Any:
    """
    Singleton loader for the reranker model (BAAI/bge-reranker-v2-m3).
    Tries FlagEmbedding first, falls back to sentence_transformers.CrossEncoder.
    """
    global _reranker_instance
    if _reranker_instance is None:
        model_name = config.RERANKER_MODEL
        device = config.RERANKER_DEVICE
        cache_folder = str(config.EMBEDDING_MODEL_CACHE_DIR) if config.EMBEDDING_MODEL_CACHE_DIR else None

        logger.info("Initializing Reranker model: %s on device: %s", model_name, device)

        try:
            from FlagEmbedding import FlagReranker  # type: ignore

            _reranker_instance = FlagReranker(
                model_name,
                use_fp16=(device != "cpu"),
                cache_dir=cache_folder,
                devices=device,
            )
            logger.info("Loaded FlagReranker successfully.")
        except Exception as exc:
            logger.info(
                "FlagReranker unavailable (%s), falling back to sentence_transformers.CrossEncoder",
                exc,
            )
            from sentence_transformers import CrossEncoder

            _reranker_instance = CrossEncoder(
                model_name,
                device=device,
                max_length=1024,
            )
            logger.info("Loaded sentence_transformers CrossEncoder successfully.")

    return _reranker_instance


def _compute_scores(reranker: Any, pairs: list[tuple[str, str]]) -> list[float]:
    """Helper to compute relevance scores for query-passage pairs."""
    compute_fn = getattr(reranker, "compute_score", None)
    if callable(compute_fn) and type(reranker).__name__ != "MagicMock":
        raw_scores = compute_fn(pairs, normalize=True)
    elif hasattr(reranker, "predict") and callable(getattr(reranker, "predict")):
        raw_scores = reranker.predict(pairs)
    elif callable(compute_fn):
        raw_scores = compute_fn(pairs, normalize=True)
    else:
        raise AttributeError("Reranker model has neither 'compute_score' nor 'predict' method.")

    if isinstance(raw_scores, (int, float)):
        return [float(raw_scores)]
    return [float(s) for s in raw_scores]


def rerank_chunks(
    query: str,
    chunks: list[Chunk],
    top_k: int = 7,
    timeout_seconds: float | None = None,
) -> tuple[list[Chunk], float, bool]:
    """
    Reranks a list of candidate Chunks (e.g. Top 20) using BGE Reranker v2 M3
    and returns the top_k most relevant chunks.

    Returns:
        tuple (reranked_chunks, elapsed_ms, fallback_used)

    Fallback Mechanism:
        If reranking fails, times out (> timeout_seconds), or disabled,
        returns the original chunks[:top_k] with fallback_used=True.
    """
    if not chunks:
        return [], 0.0, False

    if not getattr(config, "RERANKER_ENABLED", True):
        logger.info("Reranker is disabled in configuration. Using initial retrieval order.")
        return chunks[:top_k], 0.0, True

    if timeout_seconds is None:
        timeout_seconds = getattr(config, "RERANKER_TIMEOUT_SECONDS", 1.2)

    start_time = time.perf_counter()
    pairs = [(query, chunk.chunk_text) for chunk in chunks]

    try:
        reranker = get_reranker()

        if timeout_seconds > 0:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_compute_scores, reranker, pairs)
                scores = future.result(timeout=timeout_seconds)
        else:
            scores = _compute_scores(reranker, pairs)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Attach rerank score to chunks
        for chunk, score in zip(chunks, scores):
            chunk.rerank_score = float(score)

        # Sort chunks by rerank score descending
        sorted_chunks = sorted(chunks, key=lambda c: getattr(c, "rerank_score", -999.0), reverse=True)
        top_reranked = sorted_chunks[:top_k]

        logger.info(
            "Reranked %d candidates to top %d in %.2f ms (device: %s)",
            len(chunks),
            len(top_reranked),
            elapsed_ms,
            getattr(config, "RERANKER_DEVICE", "cpu"),
        )
        return top_reranked, elapsed_ms, False

    except concurrent.futures.TimeoutError:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "Reranker timed out after %.2f ms (limit: %.2fs). Falling back to initial order.",
            elapsed_ms,
            timeout_seconds,
        )
        return chunks[:top_k], elapsed_ms, True

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "Reranker error after %.2f ms: %s. Falling back to initial order.",
            elapsed_ms,
            exc,
        )
        return chunks[:top_k], elapsed_ms, True
