"use client";

import { useEffect, useState, type FormEvent } from "react";
import { documentsApi, type DocumentItem } from "@/lib/api";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void loadDocs();
    const timer = setInterval(() => { void loadDocs(); }, 5000);
    return () => clearInterval(timer);
  }, []);

  async function loadDocs() {
    try {
      const data = await documentsApi.list();
      setDocs(data.results);
    } catch {
      setError("Gagal memuat daftar dokumen.");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) { setError("Pilih file terlebih dahulu."); return; }
    if (file.size > 100 * 1024 * 1024) { setError("Ukuran file melebihi batas 100 MB."); return; }
    const formData = new FormData();
    formData.append("document", file);

    setUploading(true);
    setError(null);
    try {
      const data = await documentsApi.upload(formData);
      setMessage(data.message);
      setFile(null);
      loadDocs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload gagal.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Hapus dokumen ini?")) return;
    try {
      await documentsApi.remove(id);
      loadDocs();
    } catch {
      setError("Gagal menghapus.");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Memuat...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Dokumen Saya</h1>

      {/* Upload Zone */}
      <form onSubmit={handleUpload} className="mb-8">
        <div onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!uploading) setFile(event.dataTransfer.files[0] ?? null); }} className="border-2 border-dashed rounded-xl p-8 text-center hover:border-blue-400 transition-colors">
          <label className="cursor-pointer text-blue-600 underline">
            Pilih file
            <input type="file" name="document" className="sr-only" disabled={uploading} onChange={(event) => { setFile(event.target.files?.[0] ?? null); event.target.value = ""; }} accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.bmp,.tiff,.webp" />
          </label>
          <p className="text-gray-600">{file ? file.name : "Atau seret file ke sini"}</p>
          <p className="text-xs text-gray-400 mt-2">PDF, DOCX, TXT, JPG, PNG (maks 100MB)</p>
          <button
            type="submit"
            disabled={uploading || !file}
            className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {uploading ? "Upload..." : "Upload"}
          </button>
        </div>
        {error && <p className="mt-2 text-red-500 text-sm">{error}</p>}
        {message && <p role="status" className="mt-2 text-green-700 text-sm">{message}</p>}
      </form>

      {/* Document List */}
      {docs.length === 0 ? (
        <p className="text-gray-500 text-center py-8">Belum ada dokumen. Upload dokumen pertama!</p>
      ) : (
        <div className="space-y-3">
          {docs.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between p-4 bg-white rounded-lg shadow-sm border">
              <div>
                <p className="font-medium">{doc.document_name}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {(doc.size / 1048576).toFixed(2)} MB · {doc.file_type.toUpperCase()} ·{" "}
                  {doc.is_ocr ? "🖼️ OCR" : "📄 Teks"} ·{" "}
                  <span className={doc.status === "indexed" ? "text-green-600 font-medium" : "text-yellow-600"}>
                    {doc.status}
                  </span>
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => documentsApi.ingest(doc.id)}
                  disabled={doc.status === "indexed"}
                  className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                >
                  {doc.status === "indexed" ? "✓" : "Indeks"}
                </button>
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                >
                  Hapus
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
