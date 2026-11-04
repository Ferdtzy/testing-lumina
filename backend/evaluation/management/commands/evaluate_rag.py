"""Evaluate a fixed, manually verified set without writing chat history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from core.models import Document
from ingest import config, retrieval
from ingest.services import get_embeddings


def contains_all_terms(text: str, terms: list[str]) -> bool:
    normalized = " ".join(text.casefold().split())
    return all(term.casefold() in normalized for term in terms)


def resolve_document(case: dict) -> Document:
    """Bind golden facts to the exact indexed upload, not a reused filename."""
    matches = Document.objects.filter(
        document_name=case["document_name"],
        status=Document.Status.INDEXED,
        deleted_at__isnull=True,
    )
    for document in matches:
        path = Path(document.path_file)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == case["sha256"]:
            return document
    raise CommandError(
        f"Dokumen sumber untuk {case['id']} tidak ditemukan atau isi berkas berubah."
    )


class Command(BaseCommand):
    help = "Uji retrieval dan, opsional, jawaban RAG terhadap fakta yang dicek manual."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--with-generation", action="store_true")
        parser.add_argument("--top-k", type=int, default=config.TOP_K)

    def handle(self, *args, **options) -> None:
        if options["top_k"] < 1:
            raise CommandError("--top-k harus lebih dari nol.")
        if options["with_generation"] and not config.GEMINI_API_KEY:
            raise CommandError("GEMINI_API_KEY belum tersedia.")

        dataset = Path(__file__).resolve().parents[2] / "golden_cases.json"
        cases = json.loads(dataset.read_text(encoding="utf-8"))
        documents = {case["id"]: resolve_document(case) for case in cases}
        embeddings = get_embeddings()
        generator = None
        if options["with_generation"]:
            generator = (
                ChatPromptTemplate.from_messages([
                    ("system", config.RAG_SYSTEM_PROMPT),
                    ("human", "{question}"),
                ])
                | retrieval._build_llm()
                | StrOutputParser()
            )

        source_hits = evidence_hits = answer_hits = 0
        for case in cases:
            document = documents[case["id"]]
            vector = embeddings.embed_query(f"query: {case['question']}")
            chunks = retrieval._similarity_search(
                vector, options["top_k"], user_id=document.user_id
            )
            source_hit = any(chunk.document_id == document.id for chunk in chunks)
            evidence_hit = any(
                chunk.document_id == document.id
                and contains_all_terms(chunk.chunk_text, case["expected_terms"])
                for chunk in chunks
            )
            source_hits += source_hit
            evidence_hits += evidence_hit
            result = (
                f"{case['id']}: sumber={'ya' if source_hit else 'tidak'}, "
                f"bukti={'ya' if evidence_hit else 'tidak'}"
            )
            if generator is not None:
                expanded = retrieval._expand_visual_pairs(chunks, document.user_id)
                answer = generator.invoke({
                    "context": retrieval._format_context(expanded),
                    "question": case["question"],
                })
                answer_hit = contains_all_terms(answer, case["expected_terms"])
                answer_hits += answer_hit
                result += f", cakupan jawaban={'ya' if answer_hit else 'tidak'}"
            self.stdout.write(result)

        total = len(cases)
        self.stdout.write(
            f"Recall sumber@{options['top_k']}: {source_hits}/{total}; "
            f"bukti@{options['top_k']}: {evidence_hits}/{total}"
        )
        if generator is not None:
            self.stdout.write(
                f"Cakupan istilah jawaban: {answer_hits}/{total}. "
                "Periksa jawaban secara manual untuk menilai faithfulness."
            )
