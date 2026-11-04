"""Question/reference files and immutable corpus fingerprints."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_questions(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = read_json(path)
        rows = data.get("questions", []) if isinstance(data, dict) else data
    else:
        rows = [{"id": int(n), "question": text.strip(), "reference_answer": "", "reference_sources": []}
                for n, text in re.findall(r"^\s*(\d+)\.\s+(.+)$", path.read_text(encoding="utf-8-sig"), flags=re.M)]
    if not rows or len({str(r["id"]) for r in rows}) != len(rows):
        raise ValueError("Dataset kosong atau ID pertanyaan duplikat")
    for row in rows:
        if not isinstance(row.get("question"), str) or not row["question"].strip():
            raise ValueError("Pertanyaan kosong")
        row.setdefault("reference_answer", "")
        row.setdefault("reference_sources", [])
    return rows


def merge_references(dataset: Path, references: Path, output: Path) -> int:
    rows = read_questions(dataset)
    if references.suffix.lower() == ".csv":
        with references.open(encoding="utf-8-sig", newline="") as stream:
            refs = list(csv.DictReader(stream))
    else:
        data = read_json(references)
        refs = data.get("questions", data.get("references", [])) if isinstance(data, dict) else data
    if len({str(r["id"]) for r in refs}) != len(refs):
        raise ValueError("ID jawaban acuan duplikat")
    lookup = {str(r["id"]): r for r in refs}
    if set(lookup) - {str(r["id"]) for r in rows}:
        raise ValueError("Ada ID acuan yang tidak ada pada pertanyaan")
    count = 0
    for row in rows:
        ref = lookup.get(str(row["id"]))
        if ref and ref.get("reference_answer", "").strip():
            if ref.get("question") and ref["question"].strip() != row["question"].strip():
                raise ValueError(f"Pertanyaan berbeda pada ID {row['id']}")
            row["reference_answer"] = ref["reference_answer"].strip()
            row["reference_sources"] = ref.get("reference_sources", [])
            count += 1
    write_json(output, {"questions": rows})
    return count
