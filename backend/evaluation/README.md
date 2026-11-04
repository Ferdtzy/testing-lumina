# Evaluasi Jawaban Lumina

Pipeline penelitian terpisah dari aplikasi: tidak menulis Query, Answer, History,
migrasi, atau status dokumen. Menjalankan pertanyaan secara berurutan agar RAM
terkendali. Pengujian ini adalah evaluasi jawaban (Tabel IV); bukan hanya ablation
retrieval (Tabel III), sehingga memakai API Gemini untuk generation dan penilai.
GLM tidak digunakan pada eksperimen ini.

## Lima metrik

| Metrik | Metode | Acuan dibutuhkan |
|---|---|---|
| ROUGE-L | F1 longest common subsequence; token Unicode lowercase; tanpa stemming | Ya |
| Semantic similarity | Cosine embedding E5 jawaban vs acuan, keduanya memakai passage prefix | Ya |
| Faithfulness | Klaim didukung / seluruh klaim; ekstraksi dan pemeriksaan oleh Gemini | Tidak |
| Answer relevancy | Rata-rata cosine pertanyaan asli vs tiga pertanyaan yang dibentuk dari jawaban | Tidak |
| Answer rate | Jumlah jawaban substantif, termasuk jawaban parsial / seluruh percobaan | Tidak |

Ini implementasi custom dengan rumus faithfulness dan relevancy yang mengikuti
konsep RAGAS, bukan keluaran paket RAGAS resmi. Skor tidak boleh dibandingkan
langsung dengan eksperimen lain tanpa menyamakan model, prompt, tokenizer, dan
definisi denominator. Cosine similarity memiliki rentang teoritis -1 sampai 1;
bukan probabilitas akurasi. Answer rate tidak menyatakan kebenaran jawaban.

Pemeriksa: Gemini dengan temperature 0. Setiap klaim disertai verdict,
chunk_id, dan kutipan bukti. Kutipan diperiksa terhadap teks chunk; bukti yang
tidak ditemukan di konteks mengubah verdict menjadi insufficient. Ini pemeriksaan
penilaian AI, bukan bukti semantik yang pasti benar. Pemeriksa dapat melewatkan
klaim atau salah menafsirkan kutipan. Tidak ada klaim faktual: faithfulness null,
bukan 1. Abstention/empty: relevancy 0. Kegagalan API/judge dicatat terpisah.

Output tambahan grounded_answer_rate memakai jawaban substantif dengan
faithfulness >= 0.70 dan tanpa verdict contradicted. Ambang ini belum dikalibrasi
manusia dan bukan persentase akurasi. Jawaban yang tidak lolos disimpan sebagai
artefak audit dengan label withheld_or_unverified; tidak masuk chat aplikasi.

## Menyiapkan koleksi dan pertanyaan

Dari folder E:\PBL\lumina-ai-redesign (PowerShell):

```powershell
docker compose exec backend python -m evaluation.runner prepare --questions /app/evaluation/data/questions.md --output /app/evaluation/data/prepared --username bambang
```

Manifest membekukan ID dokumen dan hash teks/embedding/search vector chunk.
Koleksi yang berubah membatalkan run; jangan mencampur hasil sebelum/sesudah
re-ingest. Retrieval memakai filter user dan document_id SEBELUM ranking.
Dokumen acuan per pertanyaan tidak digunakan untuk membatasi retrieval: ini
akan membocorkan label dan menggelembungkan hasil.

Duplicate_groups berisi dokumen identik berdasarkan SHA256 file asli. Tentukan
koleksi final yang benar-benar akan diuji. Jangan menghapus dokumen otomatis.
Gunakan --document-ids daftar ID dipisahkan koma pada prepare untuk membekukan
koleksi yang dipilih. --acknowledge-duplicates berarti memasukkan duplikat secara
sadar; jumlah dokumen unik perlu dilaporkan. File pertanyaan tidak mempunyai
acuan: tidak ada jawaban acuan sintetis yang dibuat oleh model penguji.

## Jawaban acuan dari pengguna

Format CSV: id,question,reference_answer,reference_sources. Atau JSON:

```json
{
  "questions": [
    {
      "id": 1,
      "question": "Pertanyaan persis seperti dataset",
      "reference_answer": "Jawaban yang telah diperiksa dari sumber",
      "reference_sources": [
        {"document_id": 19, "page": 1, "quote": "Kutipan bukti"}
      ]
    }
  ]
}
```

Halaman referensi memakai nomor halaman yang dibaca pengguna, dimulai 1.
Halaman chunk asli disimpan zero-based dan juga page_display=page+1.
Import mempertahankan pertanyaan; ID tidak dikenal atau pertanyaan yang berbeda
ditolak. Jangan memakai jawaban dari model yang diuji sebagai ground truth.

```powershell
docker compose exec backend python -m evaluation.runner merge-references --dataset /app/evaluation/data/prepared/dataset.json --references /app/evaluation/data/references.json --output /app/evaluation/data/dataset_with_references.json
```

## Menjalankan uji

Reranker pada branch redesign saat diperiksa NONAKTIF, model default
BAAI/bge-reranker-v2-large, perangkat cpu. Pipeline tidak menyebutnya M3 atau CUDA
tanpa konfigurasi aktual. Opsi --enable-reranker hanya berlaku pada proses uji;
tidak mengubah konfigurasi aplikasi. Tentukan model/perangkat eksperimen dan
pakai yang sama pada seluruh run. --reranker-model dan --reranker-device tersedia.
CUDA memerlukan GPU yang benar-benar tersedia pada container. Tidak ada fallback
diam-diam: reranking gagal menjadi error, bukan hasil yang dilabeli reranker.

Mulai dengan satu pertanyaan yang sudah memiliki acuan:

```powershell
docker compose exec backend python -m evaluation.runner run --dataset /app/evaluation/data/dataset_with_references.json --manifest /app/evaluation/data/prepared/corpus_manifest.json --output /app/evaluation/results/pilot_rrf --retriever rrf --ids 56
```

Untuk konfigurasi penuh dengan reranker (contoh default model branch saat ini):

```powershell
docker compose exec backend python -m evaluation.runner run --dataset /app/evaluation/data/dataset_with_references.json --manifest /app/evaluation/data/prepared/corpus_manifest.json --output /app/evaluation/results/full_reranker --retriever rrf_reranker --enable-reranker
```

Jika manifest berisi duplikat, perintah akan berhenti sampai koleksi diperbaiki
atau --acknowledge-duplicates diberikan. Jika jawaban acuan belum lengkap,
run penuh ditolak. --allow-missing-references hanya untuk smoke test; ROUGE-L
dan semantic similarity tetap null, bukan nol atau skor buatan.

--retriever dense / fts / rrf / rrf_reranker tersedia. Semua menghasilkan maksimal
TOP_K chunk. RRF dan reranker mengambil kandidat dari daftar yang sama.
Generation dipengaruhi temperatur/provider; gunakan pengulangan terpisah untuk
benchmark, jangan menganggap hasil sekali sebagai median. --resume melanjutkan
ID yang belum selesai pada konfigurasi/dataset/corpus yang sama. Sampel gagal
tetap direkam; untuk retry gunakan folder baru dan --ids agar pemilihan hasil
terbaik tidak dilakukan diam-diam.

## Output

- results.jsonl: jawaban asli, acuan, seluruh konteks, klaim, bukti, reverse
  questions, skor, waktu tiap tahap, pemakaian token, status kegagalan.
- results.csv: hasil per pertanyaan untuk spreadsheet.
- summary.json: rerata metrik dengan evaluated_n/missing_n dan denominator rate.
- run_metadata.json: model aktif, prompt hash, corpus hash, parameter retrieval.
- dataset_snapshot.json dan corpus_manifest.json: sumber reproduksi eksperimen.

Nilai rata-rata memakai sampel yang mempunyai skor, termasuk skor 0, bukan
penggantian null menjadi 0. Coverage WAJIB dilaporkan. Answer rate memakai semua
pertanyaan yang dicoba dan null jika ada respons yang belum berhasil
diklasifikasikan. completed_run hanya true jika seluruh subset selesai; run
terputus/pilot tidak dapat dianggap sebagai hasil 100 pertanyaan.

Evaluasi menggunakan hingga empat panggilan API per pertanyaan berhasil
(generation, ekstraksi klaim, pemeriksaan klaim, reverse questions), ditambah
retry terbatas. Model diuji dan judge dapat sama: potensi bias harus dicatat.
Tidak ada perubahan data dokumen atau penggunaan API GLM.

## Validasi

```powershell
docker compose exec backend python -m unittest evaluation.test_metrics -v
docker compose exec backend python manage.py check
```

Referensi definisi:
- https://docs.ragas.io/en/v0.2.0/concepts/metrics/available_metrics/faithfulness/
- https://docs.ragas.io/en/v0.2.0/concepts/metrics/available_metrics/answer_relevance/
- https://www.microsoft.com/en-us/research/wp-content/uploads/2016/07/acl2004.pdf

## Ablation retrieval ICAE Tugas 3

Eksperimen Tugas 3 tidak memanggil LLM. Runner khusus membaca `questions.csv`
dengan kolom brief, membekukan fingerprint corpus, lalu menulis 10 hasil untuk
masing-masing konfigurasi `dense`, `text`, `rrf`, dan `lumina`. Skor yang ditulis
adalah cosine similarity, `ts_rank`, skor RRF, dan skor reranker. Halaman di
database sudah one-based sehingga tidak ditambah satu lagi.

Untuk eksperimen ICAE, sisi dense memakai indeks exact FAISS `IndexFlatIP`
dengan embedding yang dinormalisasi L2 sehingga inner product sama dengan cosine
similarity. PostgreSQL tetap menjadi sumber metadata dan full-text search, tetapi
tidak menjalankan ranking dense. Runner menyimpan `faiss.index` dan
`faiss_mapping.json` bersama hasil untuk audit reproduksi.

Sebelum Tugas 3, audit panjang token Tugas 1 pada korpus yang sama:

```bash
docker compose exec backend python -m evaluation.chunk_token_audit \
  --output /app/evaluation/results/task1/chunk_tokens.csv \
  --username NAMA_USER \
  --document-ids ID1,ID2,...,ID18
```

Jika `pct_over_512` lebih dari 10, jangan menjalankan Tugas 3 sebelum ukuran
chunk diubah menjadi 1.500 karakter dan seluruh 18 dokumen di-ingest ulang.

Jalankan hanya setelah seluruh 18 dokumen berstatus `indexed`:

```bash
docker compose exec backend python -m evaluation.retrieval_ablation \
  --questions /app/evaluation/data/questions.csv \
  --output /app/evaluation/results/task3 \
  --username NAMA_USER \
  --expected-documents 18
```

Untuk pilot satu pertanyaan sebelum run penuh, gunakan folder output berbeda:

```bash
docker compose exec backend python -m evaluation.retrieval_ablation \
  --questions /app/evaluation/data/questions.csv \
  --output /app/evaluation/results/task3-pilot \
  --username NAMA_USER \
  --expected-documents 18 \
  --limit 1
```

Setelah `retrieval.csv` selesai, hitung metrik answerable dan simpan skor
unanswerable secara terpisah:

```bash
docker compose exec backend python -m evaluation.retrieval_metrics \
  --questions /app/evaluation/data/questions.csv \
  --retrieval /app/evaluation/results/task3-faiss-v2/retrieval.csv \
  --output /app/evaluation/results/task3-faiss-v2/analysis
```

Metrik answerable dihitung pada 90 pertanyaan. Document recall adalah hit biner
terhadap `gold_doc`; document precision adalah proporsi chunk dari `gold_doc`.
Page hit mensyaratkan dokumen dan halaman benar, sedangkan gold-page recall
mengukur proporsi halaman acuan unik yang muncul. Sepuluh pertanyaan
`unanswerable` tidak diberi label relevansi buatan; skor top-1 disimpan untuk
analisis ambang abstention.

Jika proses penuh terputus, ulangi perintah yang sama dengan `--resume`. Runner
akan menolak resume bila pertanyaan, corpus, model, atau parameter berubah.
