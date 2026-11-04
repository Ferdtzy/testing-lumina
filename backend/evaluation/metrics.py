"""Auditable evaluation math, independent of Django and model providers."""
from __future__ import annotations

import math
import re
from typing import Any


def tokens(text: str) -> list[str]:
    """Unicode word tokenization; lowercase; no stemming or stopword removal."""
    return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)


def rouge_l(answer: str, reference: str) -> dict[str, float]:
    candidate, expected = tokens(answer), tokens(reference)
    previous = [0] * (len(expected) + 1)
    for word in candidate:
        current = [0]
        for i, ref_word in enumerate(expected, start=1):
            current.append(previous[i - 1] + 1 if word == ref_word else max(previous[i], current[-1]))
        previous = current
    lcs = previous[-1]
    precision = lcs / len(candidate) if candidate else 0.0
    recall = lcs / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions do not match")
    denom = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    if not denom:
        raise ValueError("Zero embedding vector")
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / denom))


def validate_claims(claims: list[dict[str, Any]], contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate judge schema and ensure cited evidence occurs in the saved context."""
    lookup = {item["chunk_id"]: item["text"] for item in contexts}
    result = []
    for item in claims:
        if not isinstance(item, dict) or not isinstance(item.get("claim"), str) or not item["claim"].strip():
            raise ValueError("Invalid claim object")
        status = item.get("verdict")
        if status not in {"supported", "contradicted", "insufficient"}:
            raise ValueError("Invalid claim verdict")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("Invalid evidence list")
        valid = []
        for citation in evidence:
            if not isinstance(citation, dict):
                raise ValueError("Invalid evidence object")
            text = str(citation.get("quote", "")).strip()
            source = lookup.get(citation.get("chunk_id"), "")
            if text and " ".join(text.split()) in " ".join(source.split()):
                valid.append(citation)
        result.append({**item, "verdict": status if valid or status == "insufficient" else "insufficient",
                       "evidence": valid, "evidence_validation_changed": status != "insufficient" and not valid})
    return result


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Macro-average available values; report coverage and rate denominators."""
    def aggregate(name: str) -> dict[str, Any]:
        values = [row["metrics"].get(name) for row in rows if row.get("metrics", {}).get(name) is not None]
        return {"mean": sum(values) / len(values) if values else None, "evaluated_n": len(values),
                "missing_n": len(rows) - len(values)}
    answered = sum(row.get("answer_status") == "substantive" for row in rows)
    verified = sum(row.get("groundedness_passed") is True and row.get("answer_status") == "substantive" for row in rows)
    unknown_grounding = sum(row.get("answer_status") == "substantive" and row.get("groundedness_passed") is None for row in rows)
    classified = sum(row.get("answer_status") in {"substantive", "abstention", "empty", "error"} for row in rows)
    return {"attempted_n": len(rows), "generation_error_n": sum(row.get("status") == "error" for row in rows),
            "judge_error_n": sum(bool(row.get("evaluation_errors")) for row in rows),
            "metrics": {name: aggregate(name) for name in ("rouge_l", "semantic_similarity", "faithfulness", "answer_relevancy")},
            "answer_rate": {"value": answered / len(rows) if rows and classified == len(rows) else None,
                            "answered_n": answered, "denominator_n": len(rows), "classified_n": classified},
            "grounded_answer_rate": {"value": verified / len(rows) if rows and classified == len(rows) and not unknown_grounding else None,
                                     "verified_n": verified, "denominator_n": len(rows), "unknown_n": unknown_grounding},
            "note": "Answer rate counts substantive responses, not correctness. Judge errors remain unknown, not zero."}
