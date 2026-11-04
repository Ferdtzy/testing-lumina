import os
import sys
import time
import django

# Set up Django environment
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lumina.settings.base')
django.setup()

from ingest.services import get_embeddings
from ingest.retrieval import (
    _similarity_search,
    _sparse_search,
    _rrf_fusion,
    _format_context,
    _build_llm,
    run_rag_query,
)
from ingest.reranker import get_reranker, rerank_chunks
from core.models import Query, Answer, History
from datetime import datetime


def format_time(ms):
    """Format milliseconds to human readable string."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.3f}s"


def main():
    print("=" * 70)
    print("RAG PIPELINE TIMING TEST (Model Load Separated)")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. Warm-up models (load separately to measure load time)
    print("[1] Loading models (one-time warm-up)...")
    start = time.time()
    embeddings = get_embeddings()
    embedding_load_time = (time.time() - start) * 1000
    print(f"  Embedding model load: {format_time(embedding_load_time)}")
    print()

    start = time.time()
    reranker = get_reranker()
    reranker_load_time = (time.time() - start) * 1000
    print(f"  Reranker model load: {format_time(reranker_load_time)}")
    print()

    # 2. Find or create a test query
    print("[2] Looking for existing queries in database...")
    start = time.time()
    question = "Apa saja matakuliah semester 2?"
    try:
        query_obj = Query.objects.filter(query_text=question).first()
        if query_obj is None:
            print("  No matching query found. Creating a test query...")
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.first()
            if user is None:
                print("  No users found either. Skipping test.")
                return
            query_obj = Query.objects.create(
                user_id=user.id,
                query_text=question,
                query_title="Test Matakuliah Semester 2",
                status="pending",
                current_step="started",
            )
            print(f"  Created query ID={query_obj.id}: '{question}'")
        else:
            print(f"  Found query ID={query_obj.id}: '{query_obj.query_text[:50]}...'")
    except Exception as e:
        print(f"  Error querying DB: {e}")
        return
    query_time = (time.time() - start) * 1000
    print(f"  Query fetch time: {format_time(query_time)}")
    print()

    question = query_obj.query_text
    query_id = query_obj.id

    # 3. Embedding generation (after model loaded)
    print("[3] Generating query embedding (using loaded model)...")
    start = time.time()
    question_vector = embeddings.embed_query(f"query: {question}")
    embedding_time = (time.time() - start) * 1000
    print(f"  Embedding generation: {format_time(embedding_time)}")
    print(f"  Vector dimension: {len(question_vector)}")
    print()

    # 4. Dense retrieval (pgvector)
    print("[4] Dense retrieval (pgvector cosine similarity)...")
    start = time.time()
    dense_chunks = _similarity_search(question_vector, top_k=20, user_id=getattr(query_obj, 'user_id', None) or None)
    dense_time = (time.time() - start) * 1000
    print(f"  Found {len(dense_chunks)} dense chunks")
    print(f"  Dense retrieval time: {format_time(dense_time)}")
    print()

    # 5. Sparse retrieval (PostgreSQL FTS)
    print("[5] Sparse retrieval (PostgreSQL Full-Text Search)...")
    start = time.time()
    sparse_chunks = _sparse_search(question, top_k=20, user_id=getattr(query_obj, 'user_id', None) or None)
    sparse_time = (time.time() - start) * 1000
    print(f"  Found {len(sparse_chunks)} sparse chunks")
    print(f"  Sparse retrieval time: {format_time(sparse_time)}")
    print()

    # 6. RRF Fusion
    print("[6] RRF (Reciprocal Rank Fusion) fusion...")
    start = time.time()
    candidates = _rrf_fusion(dense_chunks, sparse_chunks, k=60, top_k=20)
    rrf_time = (time.time() - start) * 1000
    print(f"  Candidates after RRF: {len(candidates)}")
    print(f"  RRF fusion time: {format_time(rrf_time)}")
    print()

    # 7. BGE Reranker (using loaded model)
    print("[7] BGE Reranker reranking (using loaded model)...")
    start = time.time()
    reranked, rerank_ms, fallback_used = rerank_chunks(
        question, candidates, top_k=7, timeout_seconds=5.0
    )
    rerank_time = (time.time() - start) * 1000
    fallback_str = " (fallback used)" if fallback_used else ""
    print(f"  Reranked to {len(reranked)} chunks")
    print(f"  Reranker time: {format_time(rerank_time)}{fallback_str}")
    print()

    # 8. Context formatting
    print("[8] Formatting context for LLM...")
    start = time.time()
    context = _format_context(reranked)
    context_time = (time.time() - start) * 1000
    print(f"  Context length: {len(context)} chars")
    print(f"  Context formatting time: {format_time(context_time)}")
    print()

    # 9. LLM generation
    print("[9] Generating AI response (Google Gemini)...")
    start = time.time()
    llm_result = run_rag_query(query_id=query_id, question=question)
    llm_time = (time.time() - start) * 1000
    if llm_result.get("success"):
        answer_text = llm_result.get("answer", "N/A")
        sources = llm_result.get("sources", [])
        print(f"  Answer generated: {len(answer_text)} chars")
        print(f"  Sources: {len(sources)}")
    else:
        answer_text = "FAILED"
        print(f"  LLM generation FAILED: {llm_result.get('error', 'Unknown')}")
    print(f"  LLM generation time: {format_time(llm_time)}")
    print()

    # 10. Summary
    print("=" * 70)
    print("TIMING SUMMARY (Model Load Separated)")
    print("=" * 70)
    print("--- MODEL LOAD (ONE-TIME) ---")
    print(f"  Embedding model load:        {format_time(embedding_load_time)}")
    print(f"  Reranker model load:         {format_time(reranker_load_time)}")
    total_load = embedding_load_time + reranker_load_time
    print(f"  TOTAL model load:            {format_time(total_load)}")
    print()
    print("--- PIPELINE PROCESSING (PER-QUERY) ---")
    print(f"  Embedding generation:         {format_time(embedding_time)}")
    print(f"  Dense retrieval (pgvector):   {format_time(dense_time)}")
    print(f"  Sparse retrieval (FTS):       {format_time(sparse_time)}")
    print(f"  RRF fusion:                   {format_time(rrf_time)}")
    print(f"  BGE Reranker:                 {format_time(rerank_time)}")
    print(f"  Context formatting:           {format_time(context_time)}")
    print(f"  LLM generation (Gemini):      {format_time(llm_time)}")
    pipeline_total = query_time + embedding_time + dense_time + sparse_time + rrf_time + rerank_time + context_time + llm_time
    print(f"  TOTAL pipeline processing:    {format_time(pipeline_total)}")
    print()
    print("--- COMBINED ---")
    grand_total = total_load + pipeline_total
    print(f"  Query ID: {query_id}")
    print(f"  Grand total (load + pipeline): {format_time(grand_total)}")
    print("=" * 70)
    print("Test completed!")
    print("=" * 70)

if __name__ == "__main__":
    main()
