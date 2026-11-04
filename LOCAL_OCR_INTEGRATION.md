# Local OCR / research integration

Branch: `codex/reranker-ocr-integration`
Worktree: `E:\PBL\lumina-ai-redesign`

Merged `feature/ocr-v3` into the redesign research snapshot. Local evaluation
code, ignored question/reference datasets, upload throttle and embedding batch
size are retained. Existing migration files are preserved; new migrations add
`Document.is_ocr`, `Chunk.metadata`, and merge the migration branches.

The local Compose override uses `lumina-ocr-integration:local`, initially tagged
from the already installed `lumina-ocr-tool:local`. To rebuild from source:

```powershell
docker compose build backend
docker compose up -d --no-build backend celery frontend
```

OCR model cache is persisted at `./models/paddlex`. CPU OCR uses two threads,
maximum detection side 1280, and recognition/orientation batch size 1. These
limits can be controlled with `OCR_CPU_THREADS`, `OCR_DET_MAX_SIDE`, and
`OCR_REC_BATCH_SIZE`. PDF rendering remains 250 DPI. Review small calendar text
against the original before using it as reference evidence.

The reranker model is `BAAI/bge-reranker-v2-m3`; the previous redesign default
`BAAI/bge-reranker-v2-large` could not be resolved by the model loader. Reranking
remains disabled by default, as before this integration. No CPU/GPU or retrieval
quality comparison can be inferred from mock unit tests. Record the actual
model and enabled state in each research run. Gemini Vision remains opt-in.

The database contains 20 active document records; the research collection must
explicitly select the agreed 18 documents. Existing documents have not been
re-ingested by this integration. The calendar (document 25) initially has zero
chunks and needs re-ingestion before inclusion in retrieval evaluation.

Database backup before migration: `E:\PBL\lumina-ai\pre-ocr-integration.dump`.
