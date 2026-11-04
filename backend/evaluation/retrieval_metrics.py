"""Compute auditable retrieval metrics from ICAE Task 3 output."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset import digest, write_json
from .retrieval_ablation import CONFIGS, read_brief_questions


K_VALUES = (1, 3, 5, 10)


def parse_gold_pages(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    try:
        return {int(value.strip()) for value in raw.split(";") if value.strip()}
    except ValueError as exc:
        raise ValueError(f"gold_pages tidak valid: {raw}") from exc


def reciprocal_rank(matches: list[bool], k: int = 10) -> float:
    for rank, matched in enumerate(matches[:k], start=1):
        if matched:
            return 1.0 / rank
    return 0.0


def analyze_abstention(scores: list[tuple[float, bool]]) -> dict[str, Any]:
    """Choose a top-1 reranker threshold by balanced accuracy."""
    answerable = [score for score, label in scores if label]
    unanswerable = [score for score, label in scores if not label]
    if not answerable or not unanswerable:
        raise ValueError("Analisis abstention membutuhkan kedua kelas")
    values = sorted({score for score, _ in scores})
    thresholds = [values[0] - 1e-9]
    thresholds.extend((left + right) / 2 for left, right in zip(values, values[1:]))
    thresholds.append(values[-1] + 1e-9)
    candidates = []
    for threshold in thresholds:
        tp = sum(score >= threshold and label for score, label in scores)
        fn = sum(score < threshold and label for score, label in scores)
        tn = sum(score < threshold and not label for score, label in scores)
        fp = sum(score >= threshold and not label for score, label in scores)
        answerable_accept_rate = tp / (tp + fn)
        unanswerable_reject_rate = tn / (tn + fp)
        candidates.append(
            (
                (answerable_accept_rate + unanswerable_reject_rate) / 2,
                threshold,
                answerable_accept_rate,
                unanswerable_reject_rate,
                tp,
                fn,
                tn,
                fp,
            )
        )
    best = max(candidates, key=lambda item: item[0])
    auc = sum(
        (positive > negative) + 0.5 * (positive == negative)
        for positive in answerable
        for negative in unanswerable
    ) / (len(answerable) * len(unanswerable))
    return {
        "threshold": round(best[1], 6),
        "balanced_accuracy": round(best[0], 6),
        "answerable_accept_rate": round(best[2], 6),
        "unanswerable_reject_rate": round(best[3], 6),
        "tp": best[4],
        "fn": best[5],
        "tn": best[6],
        "fp": best[7],
        "auroc": round(auc, 6),
        "answerable_n": len(answerable),
        "unanswerable_n": len(unanswerable),
    }


def evaluate_answerable(question: dict[str, str], results: list[dict[str, str]]) -> dict[str, float]:
    gold_doc = question["gold_doc"]
    gold_pages = parse_gold_pages(question["gold_pages"])
    doc_matches = [row["doc"] == gold_doc for row in results]
    page_matches = [
        row["doc"] == gold_doc
        and bool(row["page"])
        and int(row["page"]) in gold_pages
        for row in results
    ]
    metrics: dict[str, float] = {
        "doc_mrr_at_10": reciprocal_rank(doc_matches),
        "page_mrr_at_10": reciprocal_rank(page_matches),
    }
    for k in K_VALUES:
        top = results[:k]
        metrics[f"doc_recall_at_{k}"] = float(any(doc_matches[:k]))
        metrics[f"doc_precision_at_{k}"] = sum(doc_matches[:k]) / len(top) if top else 0.0
        metrics[f"page_hit_at_{k}"] = float(any(page_matches[:k]))
        found_pages = {
            int(row["page"])
            for row in top
            if row["doc"] == gold_doc and row["page"] and int(row["page"]) in gold_pages
        }
        metrics[f"gold_page_recall_at_{k}"] = len(found_pages) / len(gold_pages) if gold_pages else 0.0
    return metrics


def read_retrieval(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"qid", "config", "rank", "doc", "page", "score"}
    if not rows or required - set(rows[0]):
        raise ValueError("Kolom retrieval.csv tidak lengkap")
    keys = [(row["qid"], row["config"], row["rank"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Ada rank duplikat pada retrieval.csv")
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    metric_fields = [key for key in rows[0] if key not in {"qid", "qtype", "config"}]
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row[field]) for field in group_fields)].append(row)
    output = []
    for key, members in sorted(grouped.items()):
        result: dict[str, Any] = dict(zip(group_fields, key))
        result["n_questions"] = len(members)
        for metric in metric_fields:
            result[metric] = round(statistics.fmean(float(row[metric]) for row in members), 6)
        output.append(result)
    return output


def run(args: argparse.Namespace) -> None:
    questions = read_brief_questions(args.questions)
    retrieval = read_retrieval(args.retrieval)
    question_lookup = {row["qid"]: row for row in questions}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in retrieval:
        if row["qid"] not in question_lookup:
            raise ValueError(f"qid retrieval tidak dikenal: {row['qid']}")
        if row["config"] not in CONFIGS:
            raise ValueError(f"config tidak dikenal: {row['config']}")
        grouped[(row["qid"], row["config"])].append(row)

    expected = {(row["qid"], config) for row in questions for config in CONFIGS}
    if set(grouped) != expected:
        missing = sorted(expected - set(grouped))
        raise ValueError(f"Grup qid/config tidak lengkap: {missing[:5]}")
    for key, rows in grouped.items():
        rows.sort(key=lambda row: int(row["rank"]))
        if [int(row["rank"]) for row in rows] != list(range(1, 11)):
            raise ValueError(f"Rank tidak lengkap untuk {key}")

    per_question: list[dict[str, Any]] = []
    unanswerable: list[dict[str, Any]] = []
    for question in questions:
        for config in CONFIGS:
            results = grouped[(question["qid"], config)]
            if question["qtype"] == "unanswerable":
                unanswerable.append(
                    {
                        "qid": question["qid"],
                        "config": config,
                        "top1_score": results[0]["score"],
                        "top1_doc": results[0]["doc"],
                        "top1_page": results[0]["page"],
                    }
                )
                continue
            per_question.append(
                {
                    "qid": question["qid"],
                    "qtype": question["qtype"],
                    "config": config,
                    **evaluate_answerable(question, results),
                }
            )

    args.output.mkdir(parents=True, exist_ok=True)
    per_fields = list(per_question[0])
    summary = _aggregate(per_question, ("config",))
    by_qtype = _aggregate(per_question, ("config", "qtype"))
    _write_csv(args.output / "retrieval_per_question.csv", per_question, per_fields)
    _write_csv(args.output / "retrieval_metrics.csv", summary, list(summary[0]))
    _write_csv(args.output / "retrieval_metrics_by_qtype.csv", by_qtype, list(by_qtype[0]))
    _write_csv(
        args.output / "retrieval_unanswerable_scores.csv",
        unanswerable,
        ["qid", "config", "top1_score", "top1_doc", "top1_page"],
    )
    abstention = analyze_abstention(
        [
            (
                float(grouped[(question["qid"], "lumina")][0]["score"]),
                question["qtype"] != "unanswerable",
            )
            for question in questions
        ]
    )
    _write_csv(
        args.output / "retrieval_abstention.csv",
        [abstention],
        list(abstention),
    )
    metadata = {
        "protocol": "icae-2026-task-3-metrics",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question_sha256": digest(questions),
        "retrieval_sha256": digest(retrieval),
        "answerable_n": sum(row["qtype"] != "unanswerable" for row in questions),
        "unanswerable_n": sum(row["qtype"] == "unanswerable" for row in questions),
        "definitions": {
            "doc_recall_at_k": "Binary hit: at least one top-k chunk comes from gold_doc.",
            "doc_precision_at_k": "Fraction of top-k chunks that come from gold_doc.",
            "doc_mrr_at_10": "Reciprocal rank of the first gold_doc chunk, zero if absent in top 10.",
            "page_hit_at_k": "Binary hit: at least one top-k chunk matches gold_doc and a gold page.",
            "gold_page_recall_at_k": "Fraction of unique gold pages represented by matching top-k chunks.",
            "page_mrr_at_10": "Reciprocal rank of first chunk matching gold_doc and a gold page.",
            "abstention_threshold": "Top-1 Lumina reranker score threshold maximizing balanced accuracy on this dataset.",
        },
        "abstention": abstention,
        "abstention_caveat": "Threshold selection and evaluation use the same 100-question dataset; validate on held-out data before deployment.",
    }
    write_json(args.output / "retrieval_metrics_metadata.json", metadata)
    print(json.dumps({"output": str(args.output), **metadata}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Hitung metrik retrieval ICAE Tugas 3")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Analisis retrieval gagal: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
