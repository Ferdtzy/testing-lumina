<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

---

# Lumina Frontend — Agent Rules

Scope: everything under `frontend/`. Ini melengkapi (bukan menggantikan) `AGENTS.md` di root repo — aturan arsitektur inti, keamanan, dan larangan keras tetap berlaku dari file root. Jika ada konflik soal detail teknis frontend, file ini yang menang untuk kode di dalam `frontend/`.

## Stack di scope ini
- Next.js 16 (App Router — `app/`, bukan Pages Router)
- React + TypeScript (strict mode, hindari `any`)
- Tailwind CSS untuk semua styling

## Aturan kerja
1. **Selalu cek `node_modules/next/dist/docs/` dulu** sebelum mengubah routing, data fetching, config, atau apa pun yang berpotensi kena breaking change di Next.js 16 — jangan asumsikan API dari training data (`getServerSideProps`, config lama, dll.) masih berlaku.
2. **Jangan hapus atau edit manual blok `<!-- BEGIN:nextjs-agent-rules -->` ... `<!-- END:nextjs-agent-rules -->`** di atas. File itu di-generate ulang otomatis oleh `next dev`; kalau muncul di diff, commit apa adanya bersama perubahan lain, jangan revert manual.
3. **Semua panggilan ke backend Django lewat layer API client terpusat** (mis. `lib/api.ts` atau setara) — jangan sebar `fetch()` langsung di banyak komponen.
4. **Tidak ada logic RAG/AI (embedding, retrieval, prompt ke Gemini) di sisi frontend.** Frontend hanya menampilkan hasil dari REST API backend.
5. **Komponen baru: functional component + TypeScript**, props di-type eksplisit, tidak ada `any` kecuali benar-benar tidak terhindarkan (beri komentar alasan).
6. **Styling hanya Tailwind utility classes**; hindari inline style kecuali nilai dinamis yang tidak bisa diekspresikan lewat class.
7. **Jangan commit `.next/`, `node_modules/`, atau `.env*`** — pastikan tetap di `.gitignore`.
8. **Sebelum menyatakan task selesai**: jalankan `next build` dan/atau `next lint` dan pastikan tidak ada error TypeScript/ESLint baru.

*Untuk aturan arsitektur, keamanan, dan larangan keras yang berlaku lintas repo (backend, database, RAG pipeline), lihat `AGENTS.md` di root.*