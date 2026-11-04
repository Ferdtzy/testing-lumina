"""Audit ICAE Task 1 chunk lengths with the production E5 tokenizer."""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset import digest, write_json


CSV_FIELDS = (
    "chunk_size",
    "overlap",
    "n_chunks",
    "mean_tokens",
    "median_tokens",
    "max_tokens",
    "pct_over_512",
    "reindexed",
)


def setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")
    import django

    django.setup()


def summarize_token_lengths(lengths: list[int], *, threshold: int = 512) -> dict[str, Any]:
    if not lengths:
        raise ValueError("Corpus tidak mempunyai chunk")
    return {
        "n_chunks": len(lengths),
        "mean_tokens": round(statistics.fmean(lengths), 2),
        "median_tokens": round(statistics.median(lengths), 2),
        "max_tokens": max(lengths),
        "pct_over_512": round(100 * sum(length > threshold for length in lengths) / len(lengths), 2),
    }


def _load_corpus(username: str, raw_ids: str, expected: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from core.models import Chunk, Document, User
    from django.db.models import Q

    user = User.objects.get(username=username, is_active=True)
    document_ids = [int(value.strip()) for value in raw_ids.split(",") if value.strip()]
    if len(document_ids) != expected or len(document_ids) != len(set(document_ids)):
        raise ValueError(f"Eksperimen membutuhkan {expected} document_id unik")
    accessible = Document.objects.filter(
        id__in=document_ids,
        status=Document.Status.INDEXED,
        deleted_at__isnull=True,
    ).filter(Q(user_id=user.id) | Q(user__is_staff=True))
    if accessible.count() != expected:
        raise ValueError("Ada dokumen yang belum indexed, terhapus, atau tidak dapat diakses")
    documents = list(
        accessible.order_by("id").values("id", "document_name", "size", "updated_at")
    )
    chunks = list(
        Chunk.objects.filter(
            document_id__in=document_ids,
            document__status=Document.Status.INDEXED,
            document__deleted_at__isnull=True,
            deleted_at__isnull=True,
        )
        .filter(Q(document__user_id=user.id) | Q(document__user__is_staff=True))
        .order_by("id")
        .values("id", "document_id", "chunk_text", "updated_at")
    )
    present_ids = {row["document_id"] for row in chunks}
    missing = sorted(set(document_ids) - present_ids)
    if missing:
        raise ValueError(f"Dokumen tanpa chunk: {missing}")
    return documents, chunks


def run(args: argparse.Namespace) -> None:
    setup()
    from transformers import AutoTokenizer

    from ingest import config

    documents, chunks = _load_corpus(args.username, args.document_ids, args.expected_documents)
    tokenizer = AutoTokenizer.from_pretrained(
        config.EMBEDDING_MODEL,
        cache_dir=str(config.EMBEDDING_MODEL_CACHE_DIR) if config.EMBEDDING_MODEL_CACHE_DIR else None,
    )
    lengths: list[int] = []
    texts = [row["chunk_text"] for row in chunks]
    for start in range(0, len(texts), args.batch_size):
        encoded = tokenizer(
            texts[start : start + args.batch_size],
            add_special_tokens=True,
            truncation=False,
            padding=False,
            return_length=True,
        )
        lengths.extend(int(value) for value in encoded["length"])

    summary = summarize_token_lengths(lengths, threshold=args.threshold)
    row = {
        "chunk_size": config.CHUNK_SIZE,
        "overlap": config.CHUNK_OVERLAP,
        **summary,
        "reindexed": "no",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"Output sudah ada: {args.output}")
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(row)

    metadata_path = args.output.with_name(f"{args.output.stem}_metadata.json")
    metadata = {
        "protocol": "icae-2026-task-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": config.EMBEDDING_MODEL,
        "tokenizer": tokenizer.name_or_path,
        "threshold": args.threshold,
        "document_ids": [row["id"] for row in documents],
        "documents": documents,
        "corpus_sha256": digest(chunks),
        "result": row,
        "requires_reindex": summary["pct_over_512"] > 10,
    }
    write_json(metadata_path, metadata)
    print(json.dumps({"output": str(args.output), **metadata["result"], "requires_reindex": metadata["requires_reindex"]}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit token chunk ICAE Tugas 1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--document-ids", required=True)
    parser.add_argument("--expected-documents", type=int, default=18)
    parser.add_argument("--threshold", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1 or args.threshold < 1:
        parser.error("batch-size dan threshold minimal 1")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Tugas 1 gagal: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
