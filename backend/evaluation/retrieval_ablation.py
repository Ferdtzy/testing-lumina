"""Export the four-config retrieval ablation required by the ICAE revision brief.

This command is intentionally retrieval-only: it never invokes a generator or
writes Query/Answer/History application records.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset import digest, write_json


CONFIGS = ("dense", "text", "rrf", "lumina")
CSV_FIELDS = ("qid", "config", "rank", "doc", "page", "score")
QUESTION_FIELDS = {"qid", "gold_doc", "question", "gold_pages", "reference", "qtype"}


def setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")
    import django

    django.setup()


def read_brief_questions(path: Path, *, require_100: bool = True) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = stream.readline()
        stream.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(stream, delimiter=delimiter)
        missing = QUESTION_FIELDS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Kolom questions.csv kurang: {', '.join(sorted(missing))}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    if not rows:
        raise ValueError("questions.csv kosong")
    if require_100 and len(rows) != 100:
        raise ValueError(f"Tugas 3 membutuhkan tepat 100 pertanyaan; ditemukan {len(rows)}")
    qids = [row["qid"] for row in rows]
    if any(not qid for qid in qids) or len(set(qids)) != len(qids):
        raise ValueError("qid kosong atau duplikat")
    if any(not row["question"] for row in rows):
        raise ValueError("Ada pertanyaan kosong")
    return rows


def _user_id(username: str) -> int:
    from core.models import User

    return User.objects.get(username=username, is_active=True).pk


def _document_ids(uid: int, raw_ids: str | None, expected: int) -> list[int]:
    from core.models import Document
    from django.db.models import Q

    accessible = Document.objects.filter(
        status=Document.Status.INDEXED,
        deleted_at__isnull=True,
    ).filter(Q(user_id=uid) | Q(user__is_staff=True))
    ids = [int(value) for value in raw_ids.split(",")] if raw_ids else list(
        accessible.order_by("id").values_list("id", flat=True)
    )
    if len(ids) != len(set(ids)):
        raise ValueError("document_ids memuat ID duplikat")
    if accessible.filter(id__in=ids).count() != len(ids):
        raise ValueError("Ada dokumen yang belum indexed, terhapus, atau tidak dapat diakses")
    if len(ids) != expected:
        raise ValueError(f"Eksperimen membutuhkan {expected} dokumen indexed; ditemukan {len(ids)}")
    return sorted(ids)


def _scoped_chunks(document_ids: list[int], uid: int) -> Any:
    from core.models import Chunk
    from django.db.models import Q

    return Chunk.objects.filter(
        document_id__in=document_ids,
        document__status="indexed",
        document__deleted_at__isnull=True,
        deleted_at__isnull=True,
    ).filter(Q(document__user_id=uid) | Q(document__user__is_staff=True)).select_related("document")


def _corpus_fingerprint(document_ids: list[int], uid: int) -> dict[str, Any]:
    from core.models import Document

    documents = list(
        Document.objects.filter(id__in=document_ids)
        .order_by("id")
        .values("id", "document_name", "size", "updated_at")
    )
    for document in documents:
        document["updated_at"] = document["updated_at"].isoformat()
    chunks = list(
        _scoped_chunks(document_ids, uid)
        .order_by("id")
        .values("id", "document_id", "page", "chunk_text", "updated_at")
    )
    if not chunks:
        raise ValueError("Corpus tidak mempunyai chunk")
    zero_chunk = sorted(set(document_ids) - {row["document_id"] for row in chunks})
    if zero_chunk:
        raise ValueError(f"Dokumen tanpa chunk: {zero_chunk}")
    return {
        "documents": documents,
        "chunk_count": len(chunks),
        "corpus_sha256": digest(chunks),
    }


def _result_rows(config_name: str, chunks: list[Any], result_k: int) -> list[dict[str, Any]]:
    rows = []
    for rank, chunk in enumerate(chunks[:result_k], start=1):
        if config_name == "dense":
            score = 1.0 - float(chunk.distance)
        elif config_name == "text":
            score = float(chunk.rank)
        elif config_name == "rrf":
            score = float(chunk.rrf_score)
        else:
            score = float(chunk.rerank_score)
        rows.append(
            {
                "config": config_name,
                "rank": rank,
                "doc": chunk.document.document_name,
                # Ingestion stores page numbers as one-based values. Do not add 1 again.
                "page": "" if chunk.page is None else chunk.page,
                "score": f"{score:.6f}",
            }
        )
    return rows


def build_faiss_index(document_ids: list[int], uid: int) -> tuple[Any, list[Any]]:
    """Build an exact cosine FAISS index for the frozen experiment corpus."""
    import faiss
    import numpy as np

    chunks = list(
        _scoped_chunks(document_ids, uid)
        .filter(embedding__isnull=False)
        .order_by("id")
    )
    if not chunks:
        raise ValueError("Corpus tidak mempunyai embedding untuk FAISS")
    matrix = np.asarray([list(chunk.embedding) for chunk in chunks], dtype="float32")
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError("Dimensi embedding corpus tidak valid")
    faiss.normalize_L2(matrix)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return index, chunks


def faiss_dense_search(index: Any, chunks: list[Any], vector: list[float], top_k: int) -> list[Any]:
    """Return exact cosine-ranked chunks from an IndexFlatIP index."""
    import faiss
    import numpy as np

    query = np.asarray([vector], dtype="float32")
    if query.shape[1] != index.d:
        raise ValueError(f"Dimensi query {query.shape[1]} tidak sama dengan indeks FAISS {index.d}")
    faiss.normalize_L2(query)
    scores, positions = index.search(query, min(top_k, index.ntotal))
    results = []
    for score, position in zip(scores[0], positions[0]):
        if position < 0:
            continue
        chunk = chunks[int(position)]
        chunk.distance = 1.0 - float(score)
        results.append(chunk)
    return results


def retrieve_all(
    question: str,
    vector: list[float],
    document_ids: list[int],
    uid: int,
    faiss_index: Any,
    faiss_chunks: list[Any],
    *,
    candidate_k: int,
    result_k: int,
) -> list[dict[str, Any]]:
    from ingest import config
    from ingest.reranker import rerank_chunks
    from ingest.retrieval import _rrf_fusion, _sparse_search

    dense = faiss_dense_search(faiss_index, faiss_chunks, vector, candidate_k)
    sparse = _sparse_search(
        question,
        candidate_k,
        user_id=uid,
        document_ids=document_ids,
    )
    rrf = _rrf_fusion(dense, sparse, k=config.RRF_K, top_k=candidate_k)
    reranked, _, fallback = rerank_chunks(question, rrf, top_k=result_k, timeout_seconds=0)
    if fallback:
        raise RuntimeError("Reranker gagal atau fallback; hasil tidak boleh dilabeli lumina")

    rows: list[dict[str, Any]] = []
    rows.extend(_result_rows("dense", dense, result_k))
    rows.extend(_result_rows("text", sparse, result_k))
    rows.extend(_result_rows("rrf", rrf, result_k))
    rows.extend(_result_rows("lumina", reranked, result_k))
    return rows


def run(args: argparse.Namespace) -> None:
    setup()
    import faiss

    from ingest import config
    from ingest.services import get_embeddings

    questions = read_brief_questions(args.questions, require_100=not args.allow_partial_questions)
    if args.limit:
        questions = questions[: args.limit]
    uid = _user_id(args.username)
    document_ids = _document_ids(uid, args.document_ids, args.expected_documents)
    corpus = _corpus_fingerprint(document_ids, uid)

    config.RERANKER_ENABLED = True
    if args.reranker_model:
        config.RERANKER_MODEL = args.reranker_model
    if args.reranker_device:
        config.RERANKER_DEVICE = args.reranker_device
    if config.RERANKER_DEVICE.startswith("cuda"):
        import torch

        if not torch.cuda.is_available():
            raise ValueError("CUDA diminta tetapi tidak tersedia di container")

    args.output.mkdir(parents=True, exist_ok=True)
    faiss_index, faiss_chunks = build_faiss_index(document_ids, uid)
    partial_path = args.output / "retrieval.partial.csv"
    final_path = args.output / "retrieval.csv"
    metadata_path = args.output / "retrieval_metadata.json"
    progress_path = args.output / "retrieval_progress.json"
    metadata = {
        "protocol": "icae-2026-task-3-faiss",
        "question_sha256": digest(questions),
        "question_count": len(questions),
        "document_ids": document_ids,
        **corpus,
        "candidate_k": args.candidate_k,
        "result_k": args.result_k,
        "rrf_k": config.RRF_K,
        "embedding_model": config.EMBEDDING_MODEL,
        "dense_backend": "faiss",
        "faiss_index_type": type(faiss_index).__name__,
        "faiss_version": faiss.__version__,
        "faiss_metric": "cosine_via_l2_normalized_inner_product",
        "faiss_ntotal": int(faiss_index.ntotal),
        "reranker_model": config.RERANKER_MODEL,
        "reranker_device": config.RERANKER_DEVICE,
        "configs": list(CONFIGS),
    }
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        comparable = {
            key: value
            for key, value in previous.items()
            if key not in {"started_at", "completed_at", "actual_rows"}
        }
        if not args.resume or comparable != metadata:
            raise ValueError("Folder output sudah dipakai atau konfigurasi/corpus berubah")
    else:
        if partial_path.exists() or final_path.exists():
            raise ValueError("Folder output sudah berisi hasil tanpa metadata")
        write_json(metadata_path, {**metadata, "started_at": datetime.now(timezone.utc).isoformat()})

    faiss.write_index(faiss_index, str(args.output / "faiss.index"))
    write_json(
        args.output / "faiss_mapping.json",
        [
            {
                "position": position,
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_name": chunk.document.document_name,
                "page": chunk.page,
            }
            for position, chunk in enumerate(faiss_chunks)
        ],
    )

    completed: set[str] = set()
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        completed = set(progress.get("completed_qids", []))
    elif partial_path.exists():
        raise ValueError("Hasil parsial tidak memiliki checkpoint progress; gunakan folder output baru")

    embeddings = get_embeddings()
    new_file = not partial_path.exists()
    with partial_path.open("a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        for index, item in enumerate(questions, start=1):
            if item["qid"] in completed:
                continue
            started = time.perf_counter()
            vector = embeddings.embed_query(f"query: {item['question']}")
            rows = retrieve_all(
                item["question"],
                vector,
                document_ids,
                uid,
                faiss_index,
                faiss_chunks,
                candidate_k=args.candidate_k,
                result_k=args.result_k,
            )
            writer.writerows({"qid": item["qid"], **row} for row in rows)
            stream.flush()
            completed.add(item["qid"])
            write_json(progress_path, {"completed_qids": sorted(completed)})
            print(
                json.dumps(
                    {
                        "qid": item["qid"],
                        "progress": f"{index}/{len(questions)}",
                        "elapsed_s": round(time.perf_counter() - started, 2),
                    }
                ),
                flush=True,
            )

    current = _corpus_fingerprint(document_ids, uid)
    if current["corpus_sha256"] != corpus["corpus_sha256"]:
        raise RuntimeError("Corpus berubah selama eksperimen; hasil parsial tidak boleh digunakan")
    with partial_path.open(encoding="utf-8-sig", newline="") as stream:
        actual_rows = sum(1 for _ in csv.DictReader(stream))
    partial_path.replace(final_path)
    write_json(
        metadata_path,
        {
            **metadata,
            "started_at": json.loads(metadata_path.read_text(encoding="utf-8"))["started_at"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "actual_rows": actual_rows,
        },
    )
    progress_path.unlink(missing_ok=True)
    print(json.dumps({"output": str(final_path), "rows": actual_rows}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ekspor ablation retrieval ICAE Tugas 3")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--document-ids")
    parser.add_argument("--expected-documents", type=int, default=18)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--result-k", type=int, default=10)
    parser.add_argument("--reranker-model")
    parser.add_argument("--reranker-device")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-partial-questions", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.candidate_k < args.result_k or args.result_k < 1:
        parser.error("candidate-k harus >= result-k dan result-k minimal 1")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Tugas 3 gagal: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
