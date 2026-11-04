# AGENTS.md — Lumina

Dokumen ini adalah panduan wajib untuk semua AI coding agent (Claude Code, GitHub Copilot, Cursor, dll.) yang bekerja di repository **Lumina** — sistem RAG (Retrieval-Augmented Generation) untuk analisis dokumen cerdas, dikembangkan untuk proyek PBL IF-4MD-08 (2026).

Agent WAJIB membaca file ini secara penuh sebelum melakukan perubahan apa pun pada codebase. Jika ada instruksi dari user yang bertentangan dengan file ini, agent harus menanyakan konfirmasi terlebih dahulu, kecuali user secara eksplisit menyatakan ingin menyimpang dari aturan di sini.

---

## 1. Ringkasan Proyek

Lumina adalah aplikasi web full-stack yang memungkinkan pengguna mengunggah dokumen (PDF/DOCX), lalu melakukan tanya-jawab, perbandingan dokumen terhadap guideline, dan pembuatan soal otomatis dari dokumen tersebut menggunakan pipeline RAG hybrid (dense + sparse retrieval) dan LLM (Google Gemini).

Fitur utama:
- **Document Q&A** — tanya jawab berbasis dokumen dengan grounding & hallucination check.
- **Document Comparison** — membandingkan laporan terhadap kriteria/guideline (LLM-as-judge).
- **Question Generation** — membuat soal otomatis dari modul pembelajaran (Bloom's Taxonomy).
- **Vision processing** — memahami gambar, diagram, grafik, dan tabel di dalam dokumen (Gemini Vision).

---

## 2. Tech Stack

### Frontend (`frontend/`)
| Teknologi | Fungsi |
|---|---|
| Next.js 16 (App Router) | Web application / UI |
| React | Component framework |
| TypeScript | Type-safe frontend |
| Tailwind CSS | Styling & responsive UI |

### Backend (`backend/`)
| Teknologi | Fungsi |
|---|---|
| Django | Backend application |
| Django REST Framework | REST API |
| Python | Backend & AI processing |

### Database
| Teknologi | Fungsi |
|---|---|
| PostgreSQL | Database utama |
| pgvector | Penyimpanan embedding & vector similarity search |
| PostgreSQL Full-Text Search | Sparse/keyword retrieval untuk hybrid search |

### RAG Pipeline
- **LangChain** — orkestrasi pipeline RAG.
- **Hybrid Retrieval** — dense (pgvector) + sparse (PostgreSQL FTS), digabung dengan **RRF (Reciprocal Rank Fusion)**.
- **Metadata Filtering** — pembatasan retrieval berdasarkan `user_id`, `document_id`, `section`, dll.
- **Embedding**: Hugging Face `intfloat/multilingual-e5-large` (ingat prefix `"query: "` / `"passage: "` saat encoding).
- **Reranking**: BGE Reranker v2 M3 (cross-encoder).
- **LLM**: Google Gemini (+ Gemini Vision untuk elemen visual).

### Document & OCR Processing
- **Unstructured** — parsing dokumen dengan layout kompleks.
- **Adaptive / Structure-aware Chunking** — chunking berbasis heading/paragraf/section.
- **PaddleOCR** & **Tesseract OCR** — ekstraksi teks dari gambar/dokumen hasil scan.
- **pdf2image** — konversi halaman PDF ke gambar untuk OCR.

### Evaluation
Recall@K, Precision@K, MRR, Faithfulness, Answer Relevancy, Semantic Similarity, ROUGE, Hallucination/Groundedness Check.

### DevOps & Tooling
Docker & Docker Compose (frontend, backend, PostgreSQL), Git/GitHub, VS Code.

---

## 3. Struktur Direktori

```
lumina/
├── backend/
│   ├── core/                  # Django APP — models.py, migrations/ (data domain: dokumen, user, history, dll.)
│   ├── lumina/                 # Django PROJECT config — settings.py, urls.py, asgi.py, wsgi.py
│   └── manage.py
├── frontend/                # Next.js 16 App Router
│   ├── app/                   # Routes & pages
│   ├── public/
│   ├── AGENTS.md              # Aturan agent khusus scope frontend (lebih spesifik dari file ini)
│   └── CLAUDE.md              # (jika ada) — instruksi tambahan untuk Claude Code di scope frontend
├── docker-compose.yml
└── AGENTS.md                # File ini — berlaku untuk seluruh repo
```

> **Penting:** `backend/lumina/` bukan app RAG — itu folder config project Django (`settings.py`, `urls.py`, dsb.), namanya sama dengan nama project. `backend/core/` adalah app Django tempat model data didefinisikan. Jangan tertukar saat menambahkan app baru — app RAG baru (ingestion, retrieval, generation, evaluation) sebaiknya dibuat sebagai app terpisah, bukan ditumpuk di `core/` atau `lumina/`.

> **Catatan hierarki:** Jika ada `AGENTS.md` di dalam subfolder (mis. `frontend/AGENTS.md`), aturan di subfolder tersebut **lebih spesifik dan menang** untuk file-file di dalam scope-nya, tetapi tidak boleh bertentangan dengan aturan keamanan/arsitektur inti di file root ini.

---

## 4. Aturan Umum untuk Agent

1. **Jangan mengubah stack yang sudah ditetapkan.** Jangan mengganti Next.js↔Vue, Django↔Flask/Laravel, PostgreSQL↔MongoDB, pgvector↔FAISS, dsb., tanpa instruksi eksplisit dari user. Stack di dokumen ini adalah keputusan final proyek.
2. **Backend dan frontend berkomunikasi hanya lewat REST API** (Django REST Framework). Jangan membuat agent menulis logic RAG di sisi frontend, atau memanggil database langsung dari Next.js.
3. **Semua pemrosesan AI (embedding, retrieval, reranking, generation, OCR) terjadi di backend Django**, bukan di frontend maupun di client browser.
4. **Ikuti pola RAG hybrid yang sudah ada**: jangan menyederhanakan retrieval menjadi dense-only tanpa alasan kuat — RRF fusion adalah bagian dari desain, bukan opsional.
5. **Jaga konsistensi prefix embedding**: gunakan `"query: "` untuk teks kueri dan `"passage: "` untuk teks dokumen saat memanggil `multilingual-e5-large`, sesuai konvensi model tersebut.
6. **Metadata filtering wajib** pada setiap query retrieval yang berhubungan dengan akses user (`user_id`, `document_id`, scope) — ini adalah kontrol keamanan, bukan hanya fitur performa.
7. **Jangan hardcode kredensial, API key (termasuk Gemini API key), atau connection string.** Selalu gunakan environment variables (`.env`, Django `settings.py` via `os.environ` / `django-environ`) dan pastikan `.env` ada di `.gitignore`.
8. **Migrasi database (Django migrations) wajib dibuat setiap kali ada perubahan model**, dan jangan mengedit migration lama yang sudah pernah di-commit/dijalankan — buat migration baru.
9. **Format keluaran terstruktur (Document Comparison & Question Generation) harus tetap dalam bentuk JSON terstruktur** sesuai skema yang sudah disepakati (status sesuai/tidak sesuai/tidak ditemukan + bukti + alasan; soal + opsi + jawaban + tingkat kesulitan + metadata sumber). Jangan mengubah skema tanpa memperbarui kode konsumen di frontend.
10. **Setiap jawaban yang di-generate harus melewati groundedness/hallucination check** sebelum dikembalikan ke user — jangan menghapus langkah ini demi "menyederhanakan" pipeline.
11. **Pesan error yang ditampilkan ke user berbahasa Indonesia**, tapi log/exception detail tetap dalam bahasa teknis (English) di log file backend.
12. **Jangan menjalankan `git push`, migrasi ke production, atau perintah yang mengubah state Docker/production tanpa persetujuan eksplisit user.**

---

## 5. Konvensi Kode

### Backend (Django/Python)
- Ikuti PEP 8. Gunakan type hints pada fungsi baru.
- Struktur app Django modular: pisahkan logic RAG (ingestion, retrieval, generation, evaluation) ke dalam app Django terpisah — jangan ditumpuk di `core` (app model data) maupun di `lumina` (folder config project, bukan app).
- Gunakan Django REST Framework serializers untuk validasi input/output API — jangan mem-bypass serializer untuk parsing manual di view.
- Query PostgreSQL/pgvector lewat ORM Django atau raw SQL yang terdokumentasi jelas jika ORM tidak mendukung operasi vector tertentu.
- Async/background job (ingestion dokumen besar, OCR, evaluasi) sebaiknya tidak memblokir request-response cycle utama — gunakan task queue jika tersedia (mis. Celery) atau pola async view.

### Frontend (Next.js/TypeScript)
- Gunakan App Router (`app/`) — jangan mencampur dengan pola Pages Router lama.
- Komponen React dalam TypeScript strict mode; hindari `any`.
- Styling hanya dengan Tailwind CSS utility classes — hindari inline style kecuali kasus dinamis yang tidak bisa diekspresikan lewat class.
- Panggilan ke backend selalu lewat layer API client terpusat (mis. `lib/api.ts`), bukan `fetch()` tersebar di banyak komponen.

### Umum
- Commit message deskriptif (bahasa Indonesia atau Inggris, konsisten dengan histori commit sebelumnya di repo).
- Jangan commit file `.env`, `node_modules/`, `.next/`, `__pycache__/`, atau model/embedding cache besar — pastikan `.gitignore` mencakup semua ini.

---

## 6. Testing & Validasi Sebelum Selesai

Sebelum menyatakan sebuah task selesai, agent harus:
1. Memastikan backend Django tidak error saat `python manage.py check` / migrations applied dengan bersih.
2. Memastikan frontend build tanpa error TypeScript/ESLint (`next build` atau `next lint`).
3. Untuk perubahan pipeline RAG, jika memungkinkan jalankan skrip evaluasi yang relevan (Recall@K, Faithfulness, dll.) untuk memastikan tidak ada regresi kualitas retrieval/jawaban.
4. Tidak meninggalkan `print()`/`console.log()` debug yang tidak perlu di kode final.

---

## 7. Yang TIDAK Boleh Dilakukan Agent Tanpa Izin Eksplisit

- Mengganti komponen inti tech stack (database, framework, LLM provider, embedding model).
- Menghapus atau menulis ulang migration database yang sudah ada.
- Mengubah skema JSON terstruktur yang sudah dipakai fitur Document Comparison / Question Generation.
- Menonaktifkan groundedness/hallucination check atau metadata filtering demi kecepatan.
- Push ke branch utama (`main`/`master`) atau deploy ke production.
- Menghapus data pengguna atau dokumen yang sudah diunggah.

---

*File ini adalah sumber kebenaran (source of truth) untuk konteks arsitektur dan aturan kerja agent di repo Lumina. Perbarui file ini setiap kali ada perubahan besar pada stack atau arsitektur.*