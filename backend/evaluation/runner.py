"""Reproducible, sequential evaluation without Query/Answer/History writes."""
from __future__ import annotations

import argparse
import csv
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset import digest, merge_references, read_json, read_questions, write_json
from .metrics import cosine, rouge_l, summarize, validate_claims

logger = logging.getLogger(__name__)


def setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumina.settings")
    import django
    django.setup()


def user_id(username: str) -> int:
    from core.models import User
    return User.objects.get(username=username, is_active=True).pk


def scoped_chunks(ids: list[int], uid: int) -> Any:
    from core.models import Chunk
    from django.db.models import Q
    return Chunk.objects.filter(
        document_id__in=ids, document__status="indexed", document__deleted_at__isnull=True,
        deleted_at__isnull=True,
    ).filter(Q(document__user_id=uid) | Q(document__user__is_staff=True)).select_related("document")


def corpus_state(ids: list[int], uid: int) -> dict[str, Any]:
    from core.models import Document
    from django.db.models import Q
    docs = list(Document.objects.filter(id__in=ids, status="indexed", deleted_at__isnull=True)
                .filter(Q(user_id=uid) | Q(user__is_staff=True)).order_by("id"))
    if len(docs) != len(set(ids)):
        raise ValueError("Dokumen tidak terindeks, sudah dihapus, atau di luar akses pengguna")
    documents = []
    for doc in docs:
        path = Path(doc.path_file)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        documents.append({"id": doc.id, "name": doc.document_name, "file_sha256": file_hash,
                          "file_size": doc.size})
    records = []
    for chunk in scoped_chunks(ids, uid).order_by("id"):
        records.append({"id": chunk.id, "document_id": chunk.document_id, "page_zero_based": chunk.page,
                        "text": chunk.chunk_text, "embedding": list(chunk.embedding) if chunk.embedding is not None else None,
                        "search_vector": str(chunk.search_vector)})
    groups: dict[str, list[int]] = {}
    for doc in documents:
        if doc["file_sha256"]:
            groups.setdefault(doc["file_sha256"], []).append(doc["id"])
    return {"documents": documents, "chunk_count": len(records), "corpus_sha256": digest(records),
            "duplicate_groups": [group for group in groups.values() if len(group) > 1],
            "zero_chunk_documents": [doc["id"] for doc in documents if not any(c["document_id"] == doc["id"] for c in records)]}


def prepare(args: argparse.Namespace) -> None:
    setup()
    from core.models import Document
    uid = user_id(args.username)
    from django.db.models import Q
    ids = [int(x) for x in args.document_ids.split(",")] if args.document_ids else list(
        Document.objects.filter(status="indexed", deleted_at__isnull=True)
        .filter(Q(user_id=uid) | Q(user__is_staff=True)).values_list("id", flat=True))
    if not ids:
        raise ValueError("Tidak ada dokumen terindeks")
    rows = read_questions(args.questions)
    state = corpus_state(ids, uid)
    state.update({"created_at": datetime.now(timezone.utc).isoformat(), "user_id": uid,
                  "username": args.username, "document_ids": sorted(ids), "question_count": len(rows)})
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "dataset.json", {"questions": rows})
    write_json(args.output / "corpus_manifest.json", state)
    with (args.output / "reference_template.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "question", "reference_answer", "reference_sources"])
        writer.writeheader()
        writer.writerows({**row, "reference_sources": json.dumps(row["reference_sources"], ensure_ascii=False)} for row in rows)
    print(json.dumps({"questions": len(rows), "documents": len(ids), "chunks": state["chunk_count"],
                      "duplicate_groups": state["duplicate_groups"], "output": str(args.output)}, ensure_ascii=False))


def retrieve(question: str, vector: list[float], manifest: dict[str, Any], mode: str) -> tuple[list[Any], dict[str, Any]]:
    from django.contrib.postgres.search import SearchQuery, SearchRank
    from pgvector.django import CosineDistance
    from ingest import config
    from ingest.retrieval import _rrf_fusion
    from ingest.reranker import rerank_chunks
    qs = scoped_chunks(manifest["document_ids"], manifest["user_id"])
    start = time.perf_counter()
    dense = list(qs.filter(embedding__isnull=False).annotate(distance=CosineDistance("embedding", vector))
                 .order_by("distance", "id")[:config.DENSE_TOP_K]) if mode != "fts" else []
    query = SearchQuery(question, search_type="plain")
    sparse = list(qs.filter(search_vector__isnull=False, search_vector=query)
                  .annotate(rank=SearchRank("search_vector", query)).order_by("-rank", "id")[:config.SPARSE_TOP_K]) if mode != "dense" else []
    candidates = _rrf_fusion(dense, sparse, k=config.RRF_K, top_k=config.RERANKER_INPUT_K) if mode.startswith("rrf") else (dense if mode == "dense" else sparse)
    retrieval_ms = round((time.perf_counter() - start) * 1000)
    rerank_ms, fallback = 0.0, False
    if mode == "rrf_reranker":
        if not config.RERANKER_ENABLED:
            raise ValueError("Reranker nonaktif; gunakan --enable-reranker atau pilih --retriever rrf")
        # Benchmark completeness: do not silently report a timeout fallback as reranking.
        chunks, rerank_ms, fallback = rerank_chunks(question, candidates, top_k=config.TOP_K, timeout_seconds=0)
        if fallback:
            raise RuntimeError("Reranking gagal; sampel tidak boleh dilabeli sebagai hasil reranker")
    else:
        chunks = candidates[:config.TOP_K]
    return chunks, {"dense_ids": [c.id for c in dense], "fts_ids": [c.id for c in sparse],
                    "candidate_ids": [c.id for c in candidates], "retrieval_ms": retrieval_ms,
                    "rerank_ms": round(rerank_ms), "reranker_used": mode == "rrf_reranker", "fallback": fallback}


def evaluate(question: str, answer: str, contexts: list[dict[str, Any]], reference: str,
             models: Any, embeddings: Any) -> dict[str, Any]:
    metrics = {name: None for name in ("rouge_l", "semantic_similarity", "faithfulness", "answer_relevancy")}
    result: dict[str, Any] = {"metrics": metrics, "answer_status": "unknown", "groundedness_passed": None,
                              "evaluation_errors": [], "claims": [], "reverse_questions": []}
    if reference.strip():
        score = rouge_l(answer, reference)
        metrics["rouge_l"] = score["f1"]
        result["rouge_l_components"] = score
        try:
            vectors = embeddings.embed_documents([f"passage: {answer}", f"passage: {reference}"])
            metrics["semantic_similarity"] = cosine(vectors[0], vectors[1])
        except Exception:
            logger.exception("Semantic similarity failed")
            result["evaluation_errors"].append("semantic_similarity")
    else:
        result["reference_metrics_status"] = "pending_reference"
    try:
        extracted = models.extract(answer)
        result["answer_status"] = extracted["answer_status"]
        claims = extracted["claims"]
        if result["answer_status"] == "substantive" and not claims:
            raise ValueError("Substantive answer without extracted claims")
        if claims:
            judgments = validate_claims(models.judge_claims(claims, contexts), contexts)
            result["claims"] = judgments
            metrics["faithfulness"] = sum(c["verdict"] == "supported" for c in judgments) / len(judgments)
            result["groundedness_passed"] = metrics["faithfulness"] >= 0.7 and not any(c["verdict"] == "contradicted" for c in judgments)
        else:
            result["faithfulness_status"] = "not_applicable_no_factual_claims"
            result["groundedness_passed"] = False
    except Exception:
        logger.exception("Claim extraction or faithfulness judge failed")
        result["evaluation_errors"].append("faithfulness")
    try:
        if result["answer_status"] in {"abstention", "empty"}:
            metrics["answer_relevancy"] = 0.0
        else:
            questions = models.reverse_questions(answer)
            result["reverse_questions"] = questions
            original = embeddings.embed_query(f"query: {question}")
            scores = [cosine(original, embeddings.embed_query(f"query: {q}")) for q in questions]
            result["reverse_question_cosines"] = scores
            metrics["answer_relevancy"] = statistics.mean(scores)
    except Exception:
        logger.exception("Answer relevancy failed")
        result["evaluation_errors"].append("answer_relevancy")
    return result


def write_outputs(output: Path, rows: list[dict[str, Any]], planned_n: int) -> None:
    summary = summarize(rows)
    summary.update({"planned_n": planned_n, "completed_run": len(rows) == planned_n,
                    "protocol": "lumina-evaluation-v1-custom-not-ragas-package"})
    write_json(output / "summary.json", summary)
    fields = ["id", "status", "answer_status", "rouge_l", "semantic_similarity", "faithfulness",
              "answer_relevancy", "groundedness_passed", "response_time_ms", "question", "answer", "reference_answer"]
    with (output / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**row, **row.get("metrics", {})} for row in rows)


def run(args: argparse.Namespace) -> None:
    setup()
    from ingest import config
    from ingest.services import get_embeddings
    from ingest.retrieval import _format_context
    from .providers import Models
    rows = read_questions(args.dataset)
    manifest = read_json(args.manifest)
    uid = user_id(manifest["username"])
    if uid != manifest["user_id"] or corpus_state(manifest["document_ids"], uid)["corpus_sha256"] != manifest["corpus_sha256"]:
        raise ValueError("Koleksi dokumen berubah; buat manifest baru dan jangan campur hasil")
    if manifest["duplicate_groups"] and not args.acknowledge_duplicates:
        raise ValueError("Koleksi berisi duplikat; tentukan koleksi atau gunakan --acknowledge-duplicates secara eksplisit")
    if args.ids:
        wanted = {str(x) for x in args.ids.split(",")}
        if wanted - {str(r["id"]) for r in rows}:
            raise ValueError("ID pertanyaan tidak ditemukan")
        rows = [r for r in rows if str(r["id"]) in wanted]
    if args.limit:
        rows = rows[:args.limit]
    if not args.allow_missing_references and any(not r["reference_answer"].strip() for r in rows):
        raise ValueError("Jawaban acuan belum lengkap; gunakan merge-references sebelum pengujian penuh")
    if args.enable_reranker:
        config.RERANKER_ENABLED = True
    if args.reranker_model:
        config.RERANKER_MODEL = args.reranker_model
    if args.reranker_device:
        config.RERANKER_DEVICE = args.reranker_device
    if args.retriever == "rrf_reranker" and not config.RERANKER_ENABLED:
        raise ValueError("Reranker aktif belum tersedia; tambahkan --enable-reranker untuk proses evaluasi saja")
    if args.retriever != "rrf_reranker" and (args.enable_reranker or args.reranker_model or args.reranker_device):
        raise ValueError("Parameter reranker hanya berlaku untuk --retriever rrf_reranker")
    if args.reranker_device and args.reranker_device.startswith("cuda"):
        import torch
        if not torch.cuda.is_available():
            raise ValueError("Container tidak memiliki akses CUDA")
    versions = {}
    for package in ("Django", "langchain-google-genai", "langchain-huggingface", "sentence-transformers", "torch", "pgvector"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    metadata = {"protocol_version": 1, "implementation_sha256": digest({p.name: p.read_text(encoding="utf-8") for p in Path(__file__).parent.glob("*.py") if not p.name.startswith("test_")}),
                "versions": versions, "dataset_sha256": digest(rows), "corpus_sha256": manifest["corpus_sha256"],
                "document_ids": manifest["document_ids"], "duplicate_groups": manifest["duplicate_groups"],
                "retriever": args.retriever, "models": {key: getattr(config, key) for key in
                 ("GEMINI_MODEL", "GEMINI_TEMPERATURE", "GEMINI_MAX_TOKENS", "EMBEDDING_MODEL", "EMBEDDING_DEVICE",
                  "RERANKER_MODEL", "RERANKER_DEVICE", "RERANKER_ENABLED", "RERANKER_INPUT_K", "TOP_K", "RRF_K",
                  "DENSE_TOP_K", "SPARSE_TOP_K")}, "judge_model": args.judge_model or config.GEMINI_MODEL,
                "prompt_sha256": digest(config.RAG_SYSTEM_PROMPT), "python": platform.python_version(),
                "missing_references_allowed": args.allow_missing_references}
    if args.dry_run:
        print(json.dumps({"validated_questions": len(rows), "configuration": metadata, "api_calls": 0}, ensure_ascii=False))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output / "run_metadata.json"
    records_path = args.output / "results.jsonl"
    existing: list[dict[str, Any]] = []
    if metadata_path.exists():
        previous = read_json(metadata_path)
        if not args.resume or previous["configuration"] != metadata:
            raise ValueError("Folder hasil sudah digunakan atau konfigurasi berubah; gunakan folder baru atau --resume")
        if records_path.exists():
            existing = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        write_json(metadata_path, {"started_at": datetime.now(timezone.utc).isoformat(), "configuration": metadata})
    write_json(args.output / "dataset_snapshot.json", {"questions": rows})
    write_json(args.output / "corpus_manifest.json", manifest)
    embeddings = get_embeddings()
    models = Models(args.judge_model, args.timeout)
    completed = {str(r["id"]) for r in existing}
    with records_path.open("a", encoding="utf-8") as stream:
        for question in rows:
            if str(question["id"]) in completed:
                continue
            start = time.perf_counter()
            record: dict[str, Any] = {**question, "started_at": datetime.now(timezone.utc).isoformat(),
                                      "status": "error", "answer_status": "error", "answer": "", "metrics": {}}
            call_start = len(models.calls)
            try:
                embed_start = time.perf_counter()
                vector = embeddings.embed_query(f"query: {question['question']}") if args.retriever != "fts" else []
                record["embedding_ms"] = round((time.perf_counter() - embed_start) * 1000)
                chunks, retrieval = retrieve(question["question"], vector, manifest, args.retriever)
                record["retrieval"] = retrieval
                contexts = [{"chunk_id": c.id, "document_id": c.document_id, "document_name": c.document.document_name,
                             "page_zero_based": c.page, "page_display": c.page + 1 if c.page is not None else None,
                             "text": c.chunk_text} for c in chunks]
                record["contexts"] = contexts
                if not chunks:
                    record.update({"status": "no_context", "answer_status": "abstention", "groundedness_passed": False})
                else:
                    answer = models.generate(question["question"], _format_context(chunks))
                    record["raw_answer"] = answer
                    # Evaluation artifact retains the generated text for auditing; the app's history is untouched.
                    record["answer"] = answer
                    record.update(evaluate(question["question"], answer, contexts, question["reference_answer"], models, embeddings))
                    record["status"] = "evaluated" if not record["evaluation_errors"] else "partial_evaluation"
                    record["answer_release_status"] = "verified" if record["groundedness_passed"] else "withheld_or_unverified"
            except Exception as exc:
                logger.exception("Evaluation failed for question %s", question["id"])
                record["error_type"] = type(exc).__name__
                record["error_category"] = "service_unavailable" if "503" in str(exc) else "rate_limit" if "429" in str(exc) else "pipeline_error"
            record["response_time_ms"] = round((time.perf_counter() - start) * 1000)
            record["api_calls"] = models.calls[call_start:]
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            stream.flush()
            existing.append(record)
            write_outputs(args.output, existing, len(rows))
            print(json.dumps({"id": question["id"], "status": record["status"], "answer_status": record["answer_status"],
                              "metrics": record["metrics"]}, ensure_ascii=False), flush=True)
    write_outputs(args.output, existing, len(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluasi jawaban Lumina tanpa mengubah data aplikasi")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--questions", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--username", default="bambang")
    prep.add_argument("--document-ids")
    merge = sub.add_parser("merge-references")
    merge.add_argument("--dataset", type=Path, required=True)
    merge.add_argument("--references", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--dataset", type=Path, required=True)
    execute.add_argument("--manifest", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--retriever", choices=["dense", "fts", "rrf", "rrf_reranker"], default="rrf_reranker")
    execute.add_argument("--enable-reranker", action="store_true")
    execute.add_argument("--reranker-model")
    execute.add_argument("--reranker-device")
    execute.add_argument("--judge-model")
    execute.add_argument("--timeout", type=float, default=90)
    execute.add_argument("--limit", type=int)
    execute.add_argument("--ids")
    execute.add_argument("--resume", action="store_true")
    execute.add_argument("--allow-missing-references", action="store_true")
    execute.add_argument("--acknowledge-duplicates", action="store_true")
    execute.add_argument("--dry-run", action="store_true", help="Validasi konfigurasi tanpa memanggil model")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "merge-references":
        print("Jawaban acuan digabungkan:", merge_references(args.dataset, args.references, args.output))
    else:
        run(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Evaluation stopped")
        print(f"Evaluasi tidak dapat dijalankan: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
