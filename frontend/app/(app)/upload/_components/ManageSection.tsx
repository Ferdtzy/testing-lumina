"use client";

import { Fragment, useState, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";
import DocumentStats from "./DocumentStats";
import UploadModal from "./UploadModal";

interface DocumentItem {
    id: number;
    document_name: string;
    file_type?: string;
    size_human?: string | null;
    size: number;
    status: string;
    created_at: string;
    chunk_count?: number;
}

interface DocumentChunk {
    id: number;
    chunk_text: string;
}

interface IngestLog {
    id: number;
    step: string;
    message: string;
    created_at: string;
}

type OpenDetail = { documentId: number; type: "chunks" | "logs" } | null;

export default function ManageSection() {
    const router = useRouter();
    const user = getUser();
    const isAdmin = user?.role === "admin" && user.is_staff === true;

    const [docs, setDocs] = useState<DocumentItem[]>([]);
    const [loadingDocs, setLoadingDocs] = useState(true);
    const [stats, setStats] = useState({ total: 0, indexed: 0, processing: 0, failed: 0 });
    const [search, setSearch] = useState("");
    const [openDetail, setOpenDetail] = useState<OpenDetail>(null);
    const [chunks, setChunks] = useState<DocumentChunk[]>([]);
    const [logs, setLogs] = useState<IngestLog[]>([]);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [openMenuId, setOpenMenuId] = useState<number | null>(null);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [typeFilter, setTypeFilter] = useState<string>("all");
    const [dateSort, setDateSort] = useState<string>("newest");
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const menuRef = useRef<HTMLDivElement>(null);
    const docRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());

    useEffect(() => {
        if (!isAdmin) router.replace("/");
    }, [isAdmin, router]);

    const [isUploadOpenState, setIsUploadOpenState] = useState(false);

    const refreshDocs = async (page: number = 1) => {
        setLoadingDocs(true);
        try {
            const params = new URLSearchParams({
                page: page.toString(),
                limit: "10",
            });
            if (statusFilter !== "all") params.append("status", statusFilter);
            if (typeFilter !== "all") params.append("file_type", typeFilter);
            if (search) params.append("document_name", search);

            const response = await api.get<{
                count: number;
                next: string | null;
                previous: string | null;
                results: DocumentItem[];
            }>(`/documents/?${params.toString()}`);

            setDocs(response.results);
            setTotalPages(Math.ceil(response.count / 10));
            setCurrentPage(page);
        } catch {
            setDocs([]);
        } finally {
            setLoadingDocs(false);
        }
    };

    const fetchSummary = async () => {
        try {
            const data = await api.get<{
                total: number;
                indexed: number;
                processing: number;
                failed: number;
            }>("/documents/summary/");
            setStats(data);
        } catch {
            setStats({ total: 0, indexed: 0, processing: 0, failed: 0 });
        }
    };

    useEffect(() => {
        const timer = window.setTimeout(() => {
            void Promise.all([refreshDocs(1), fetchSummary()]);
        }, 0);

        return () => window.clearTimeout(timer);
    }, [statusFilter, typeFilter, dateSort]);

    useEffect(() => {
        const hasProcessing = docs.some(
            (doc) =>
                doc.status.toLowerCase() === "processing" ||
                doc.status.toLowerCase() === "pending",
        );

        if (!hasProcessing) return;

        const intervalId = setInterval(() => {
            refreshDocs(currentPage);
        }, 3000);

        return () => clearInterval(intervalId);
    }, [docs, currentPage]);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setOpenMenuId(null);
            }
        }

        if (openMenuId !== null) {
            document.addEventListener("mousedown", handleClickOutside);
        } else {
            document.removeEventListener("mousedown", handleClickOutside);
        }

        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, [openMenuId, menuRef]);

    const filteredDocs = useMemo(() => {
        let result = [...docs];

        if (search) {
            result = result.filter((doc) =>
                doc.document_name
                    .toLocaleLowerCase("id-ID")
                    .includes(search.toLocaleLowerCase("id-ID")),
            );
        }

        if (statusFilter !== "all") {
            const statusMap: Record<string, string[]> = {
                indexed: ["indexed", "completed", "success"],
                processing: ["processing", "pending"],
                failed: ["failed", "error"],
            };

            const filterStatuses = statusMap[statusFilter.toLowerCase()] || [];

            result = result.filter((doc) => {
                const docStatus = doc.status.toLowerCase();
                return filterStatuses.some((s) => docStatus === s);
            });
        }

        if (typeFilter !== "all") {
            const normalizedType = typeFilter.toLowerCase();
            result = result.filter((doc) => {
                const docType = (doc.file_type || "").toLowerCase();
                return docType === normalizedType;
            });
        }

        return result;
    }, [docs, search, statusFilter, typeFilter]);

    const sortedDocs = useMemo(() => {
        const result = [...filteredDocs];

        result.sort((a, b) => {
            if (dateSort === "newest") {
                return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
            } else {
                return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
            }
        });

        return result;
    }, [filteredDocs, dateSort]);

    const allSelected = sortedDocs.length > 0 && sortedDocs.every(doc => selectedIds.has(doc.id));
    const someSelected = sortedDocs.some(doc => selectedIds.has(doc.id));

    function toggleSelectAll() {
        if (allSelected) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(sortedDocs.map(doc => doc.id)));
        }
    }

    function toggleSelect(id: number) {
        const newSet = new Set(selectedIds);
        if (newSet.has(id)) {
            newSet.delete(id);
        } else {
            newSet.add(id);
        }
        setSelectedIds(newSet);
    }

    async function handleBulkDelete() {
        if (selectedIds.size === 0) return;

        if (!window.confirm(`Hapus ${selectedIds.size} dokumen yang dipilih?`)) {
            return;
        }

        const results = await Promise.allSettled(
            Array.from(selectedIds).map(id => api.delete(`/documents/${id}/`))
        );

        const failed = results.filter(r => r.status === "rejected").length;
        if (failed > 0) {
            setUploadError(`${failed} dokumen gagal dihapus.`);
        }

        setSelectedIds(new Set());
        await refreshDocs(currentPage);
    }

    async function handleBulkReIngest() {
        if (selectedIds.size === 0) return;

        const results = await Promise.allSettled(
            Array.from(selectedIds).map(id => api.post(`/ingest/${id}/re-ingest/`, {}))
        );

        const failed = results.filter(r => r.status === "rejected").length;
        if (failed > 0) {
            setUploadError(`${failed} dokumen gagal di-re-ingest.`);
        }

        setSelectedIds(new Set());
        await refreshDocs(currentPage);
    }

    async function toggleDetail(doc: DocumentItem, type: "chunks" | "logs") {
        if (openDetail?.documentId === doc.id && openDetail.type === type) {
            setOpenDetail(null);
            return;
        }

        if (type === "chunks" || type === "logs") {
            setDocs((prevDocs) => {
                const targetDoc = prevDocs.find((d) => d.id === doc.id);
                if (!targetDoc) return prevDocs;
                const otherDocs = prevDocs.filter((d) => d.id !== doc.id);
                return [targetDoc, ...otherDocs];
            });
        }

        setOpenDetail({ documentId: doc.id, type });
        setLoadingDetail(true);

        try {
            if (type === "chunks") {
                const data = await api.get<{ results: DocumentChunk[] }>(`/documents/${doc.id}/chunks/`);

                setChunks(Array.isArray(data?.results) ? data.results : []);
            } else {
                const data = await api.get<{ results: IngestLog[] }>(
                    `/documents/${doc.id}/ingest_logs/`,
                );

                setLogs(Array.isArray(data?.results) ? data.results : []);
            }
        } catch (error) {
            console.error(`Failed to fetch ${type} for document ${doc.id}:`, error);
            if (type === "chunks") {
                setChunks([]);
            } else {
                setLogs([]);
            }
        } finally {
            setLoadingDetail(false);

            setTimeout(() => {
                const el = docRefs.current.get(doc.id);
                if (el) {
                    el.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }, 50);
        }
    }

    async function handleDelete(doc: DocumentItem) {
        if (
            !window.confirm(
                `Hapus dokumen "${doc.document_name}" beserta seluruh chunk-nya?`,
            )
        ) {
            return;
        }

        try {
            await api.delete(`/documents/${doc.id}/`);

            if (openDetail?.documentId === doc.id) {
                setOpenDetail(null);
            }

            if (openMenuId === doc.id) {
                setOpenMenuId(null);
            }

            await Promise.all([refreshDocs(currentPage), fetchSummary()]);
        } catch {
            return;
        }
    }

    async function handleReIngest(doc: DocumentItem) {
        try {
            await api.post(`/ingest/${doc.id}/re-ingest/`, {});

            setOpenMenuId(null);
            await Promise.all([refreshDocs(currentPage), fetchSummary()]);
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : "Gagal memulai re-ingest dokumen.";
            setUploadError(msg);
        }
    }

    async function submitUpload(file: File) {
        setIsUploading(true);
        setUploadError(null);

        try {
            const formData = new FormData();
            formData.append("document", file);
            await api.uploadFile("/ingest/upload/", formData);
            setIsUploadOpenState(false);
            await Promise.all([refreshDocs(1), fetchSummary()]);
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : "Gagal mengunggah dokumen.";
            setUploadError(msg);
        } finally {
            setIsUploading(false);
        }
    }

    if (!isAdmin) {
        return (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[#1a3a52]/70">
                Anda tidak memiliki izin untuk mengakses halaman upload.
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col overflow-hidden">
            <div className="flex min-h-0 flex-1 flex-col gap-4 p-5">
                <DocumentStats stats={stats} />

                <div className="shrink-0 flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-[200px] flex items-center gap-3 rounded-2xl px-4 py-3 [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] [box-shadow:0_2px_4px_rgba(0,0,0,0.15)] [backdrop-filter:blur(20px)] [-webkit-backdrop-filter:blur(20px)]">
                        <svg className="h-5 w-5 shrink-0 text-[#1a3a52]/45" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" />
                        </svg>
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Cari dokumen..."
                            className="w-full bg-transparent text-sm text-[#1a3a52] outline-none placeholder:text-[#1a3a52]/40"
                        />
                    </div>

                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="rounded-xl px-3 py-2 text-sm text-[#1a3a52] [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] outline-none"
                    >
                        <option value="all">Semua Status</option>
                        <option value="indexed">Indexed</option>
                        <option value="processing">Processing</option>
                        <option value="failed">Failed</option>
                    </select>

                    <select
                        value={typeFilter}
                        onChange={(e) => setTypeFilter(e.target.value)}
                        className="rounded-xl px-3 py-2 text-sm text-[#1a3a52] [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] outline-none"
                    >
                        <option value="all">Semua Tipe</option>
                        <option value="pdf">PDF</option>
                        <option value="docx">DOCX</option>
                        <option value="txt">TXT</option>
                    </select>

                    <select
                        value={dateSort}
                        onChange={(e) => setDateSort(e.target.value)}
                        className="rounded-xl px-3 py-2 text-sm text-[#1a3a52] [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] outline-none"
                    >
                        <option value="newest">Terbaru</option>
                        <option value="oldest">Terlama</option>
                    </select>

                    <button
                        type="button"
                        onClick={() => {
                            setIsUploadOpenState(true);
                            setUploadError(null);
                        }}
                        className="rounded-xl bg-[#1a6fa8] px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-[#155a85]"
                    >
                        + Upload Dokumen
                    </button>

                    <button
                        type="button"
                        onClick={() => refreshDocs(1)}
                        className="rounded-xl px-3 py-2 text-sm text-[#1a3a52]/70 transition-colors hover:bg-white/15"
                    >
                        Muat ulang
                    </button>
                </div>

                {someSelected && (
                    <div className="shrink-0 flex items-center gap-3 rounded-xl bg-[#1a6fa8]/10 px-4 py-3">
                        <span className="text-sm text-[#1a3a52]">
                            {selectedIds.size} dipilih
                        </span>
                        <button
                            type="button"
                            onClick={() => void handleBulkReIngest()}
                            className="rounded-lg bg-[#1a6fa8] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[#155a85]"
                        >
                            <span className="flex items-center gap-1.5">
                                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                                </svg>
                                Re-ingest
                            </span>
                        </button>
                        <button
                            type="button"
                            onClick={() => void handleBulkDelete()}
                            className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700"
                        >
                            <span className="flex items-center gap-1.5">
                                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                                </svg>
                                Hapus
                            </span>
                        </button>
                        <button
                            type="button"
                            onClick={() => setSelectedIds(new Set())}
                            className="rounded-lg px-3 py-1.5 text-xs text-[#1a3a52]/70 transition-colors hover:bg-white/15"
                        >
                            Batal
                        </button>
                    </div>
                )}

                <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] [box-shadow:0_2px_4px_rgba(0,0,0,0.15)] [backdrop-filter:blur(20px)] [-webkit-backdrop-filter:blur(20px)]">
                    <div className="overflow-auto flex-1">
                        <table className="w-full table-fixed text-sm">
                            <thead className="sticky top-0 bg-white/95 backdrop-blur-sm z-10">
                                <tr className="border-b border-white/10">
                                    <th className="w-[4%] p-4">
                                        <input
                                            type="checkbox"
                                            checked={allSelected}
                                            onChange={toggleSelectAll}
                                            className="h-4 w-4 rounded border-gray-300"
                                        />
                                    </th>
                                    <th className="w-[36%] text-left p-4 font-medium text-[#1a3a52]">Nama dokumen</th>
                                    <th className="w-[10%] text-left p-4 font-medium text-[#1a3a52]">Tipe</th>
                                    <th className="w-[10%] text-left p-4 font-medium text-[#1a3a52]">Ukuran</th>
                                    <th className="w-[14%] text-left p-4 font-medium text-[#1a3a52]">Tanggal</th>
                                    <th className="w-[8%] text-center p-4 font-medium text-[#1a3a52]">Chunk</th>
                                    <th className="w-[10%] text-left p-4 font-medium text-[#1a3a52]">Status</th>
                                    <th className="w-[8%] text-center p-4 font-medium text-[#1a3a52]">Aksi</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loadingDocs ? (
                                    <tr>
                                        <td colSpan={8} className="p-6 text-center text-sm text-[#1a3a52]/50">
                                            Memuat dokumen...
                                        </td>
                                    </tr>
                                ) : sortedDocs.length === 0 ? (
                                    <tr>
                                        <td colSpan={8} className="p-8 text-center text-sm text-[#1a3a52]/50">
                                            Tidak ada dokumen yang ditemukan.
                                        </td>
                                    </tr>
                                ) : (
                                    sortedDocs.map((doc) => {
                                        const chunkCount = doc.chunk_count ?? 0;
                                        const isExpanded = openDetail?.documentId === doc.id;
                                        const isChunks = openDetail?.type === "chunks";

                                        const detailRow = isExpanded ? (
                                            <tr key={`detail-${doc.id}`} className="bg-white/5">
                                                <td colSpan={8} className="p-0">
                                                    <div className="overflow-hidden border-t border-white/10 bg-white/10">
                                                        <div className="p-4">
                                                            <h4 className="mb-3 text-sm font-semibold text-[#1a3a52]">
                                                                {isChunks ? `Chunk (${chunks.length} item)` : `Ingest Log (${logs.length} item)`}
                                                            </h4>
                                                            {loadingDetail ? (
                                                                <p className="text-sm text-[#1a3a52]/50">Memuat data...</p>
                                                            ) : isChunks ? (
                                                                chunks.length === 0 ? (
                                                                    <p className="text-sm text-[#1a3a52]/50">Tidak ada chunk tersedia.</p>
                                                                ) : (
                                                                    <div className="max-h-64 overflow-y-auto space-y-3 pr-2">
                                                                        {chunks.map((chunk, index) => (
                                                                            <div key={chunk.id} className="rounded-lg bg-white/5 p-3">
                                                                                <div className="mb-1 flex items-center justify-between">
                                                                                    <span className="text-xs font-medium text-[#1a6fa8]">
                                                                                        Chunk {index + 1}
                                                                                    </span>
                                                                                </div>
                                                                                <p className="whitespace-pre-wrap text-xs leading-relaxed text-[#1a3a52]/80">
                                                                                    {chunk.chunk_text}
                                                                                </p>
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                )
                                                            ) : logs.length === 0 ? (
                                                                <p className="text-sm text-[#1a3a52]/50">Tidak ada log tersedia.</p>
                                                            ) : (
                                                                <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
                                                                    {logs.map((log) => (
                                                                        <div key={log.id} className="rounded-lg bg-white/5 p-3">
                                                                            <div className="mb-1 flex items-center justify-between">
                                                                                <span className="text-xs font-medium text-[#1a6fa8]">
                                                                                    {log.step}
                                                                                </span>
                                                                                <span className="text-[10px] text-[#1a3a52]/40">
                                                                                    {log.created_at}
                                                                                </span>
                                                                            </div>
                                                                            <p className="text-xs text-[#1a3a52]/70">
                                                                                {log.message}
                                                                            </p>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                        ) : null;

                                        return (
                                            <Fragment key={doc.id}>
                                                <tr>
                                                    <td className="p-4 text-center">
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedIds.has(doc.id)}
                                                            onChange={() => toggleSelect(doc.id)}
                                                            className="h-4 w-4 rounded border-gray-300"
                                                        />
                                                    </td>
                                                    <td className="p-4">
                                                        <p className="truncate text-sm font-medium text-[#1a3a52]">
                                                            {doc.document_name}
                                                        </p>
                                                    </td>
                                                    <td className="p-4">
                                                        <div className="flex items-center gap-2">
                                                            {doc.file_type?.toLowerCase() === "pdf" && (
                                                                <svg className="h-4 w-4 text-red-500" fill="currentColor" viewBox="0 0 24 24">
                                                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zm-2.5 9.5c0 .83-.67 1.5-1.5 1.5H8v2H6.5v-6H9c.83 0 1.5.67 1.5 1.5v1zm5 0c0 .83-.67 1.5-1.5 1.5h-1v2h-1.5v-6h2.5c.83 0 1.5.67 1.5 1.5v1zm4.5-1.5h-2v1h2v1.5h-2v1.5h-1.5v-6h3.5v1z"/>
                                                                </svg>
                                                            )}
                                                            {doc.file_type?.toLowerCase() === "docx" && (
                                                                <svg className="h-4 w-4 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
                                                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM8 12h8v2H8v-2zm0 4h8v2H8v-2z"/>
                                                                </svg>
                                                            )}
                                                            {doc.file_type?.toLowerCase() === "txt" && (
                                                                <svg className="h-4 w-4 text-gray-500" fill="currentColor" viewBox="0 0 24 24">
                                                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM8 12h8v2H8v-2zm0 4h8v2H8v-2z"/>
                                                                </svg>
                                                            )}
                                                            <span className="text-xs text-[#1a3a52]/60">
                                                                {doc.file_type?.toUpperCase() || "-"}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="p-4">
                                                        <p className="text-xs text-[#1a3a52]/60">
                                                            {doc.size_human ?? `${Math.round(doc.size / 1024)} KB`}
                                                        </p>
                                                    </td>
                                                    <td className="p-4">
                                                        <p className="text-xs text-[#1a3a52]/60">
                                                            {new Date(doc.created_at).toLocaleDateString("id-ID", {
                                                                day: "numeric",
                                                                month: "short",
                                                                year: "numeric",
                                                            })}
                                                        </p>
                                                    </td>
                                                    <td className="p-4 text-center">
                                                        <p className="text-xs text-[#1a3a52]/60">
                                                            {chunkCount}
                                                        </p>
                                                    </td>
                                                    <td className="p-4">
                                                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide ${
                                                            ["indexed", "completed", "success"].includes(doc.status.toLowerCase())
                                                                ? "text-green-600 bg-green-50"
                                                                : ["processing", "pending"].includes(doc.status.toLowerCase())
                                                                    ? "text-orange-600 bg-orange-50"
                                                                    : ["failed", "error"].includes(doc.status.toLowerCase())
                                                                        ? "text-red-600 bg-red-50"
                                                                        : "text-[#1a3a52]/60 bg-white/15"
                                                        }`}>
                                                            {["processing", "pending"].includes(doc.status.toLowerCase()) && (
                                                                <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                                                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
                                                                </svg>
                                                            )}
                                                            {doc.status.toLowerCase().replace(/^./, doc.status[0].toUpperCase())}
                                                        </span>
                                                    </td>
                                                    <td className="p-2 text-center">
                                                        <div className="relative inline-block">
                                                            <button
                                                                onClick={() =>
                                                                    setOpenMenuId(
                                                                        openMenuId === doc.id ? null : doc.id,
                                                                    )
                                                                }
                                                                className="flex h-7 w-7 items-center justify-center rounded-full text-[#1a6fa8] hover:bg-[#1a6fa8]/20 transition-colors"
                                                            >
                                                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01" />
                                                                </svg>
                                                            </button>
                                                            {openMenuId === doc.id && (
                                                                <div ref={menuRef} className="absolute right-0 z-10 mt-1 w-48 origin-top-right rounded-md bg-white shadow-2xl ring-1 ring-black/20">
                                                                    <div className="py-1">
                                                                        <button
                                                                            onClick={() => {
                                                                                toggleDetail(doc, "chunks");
                                                                                setOpenMenuId(null);
                                                                            }}
                                                                            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-[#1a6fa8] hover:bg-[#1a6fa8]/10"
                                                                        >
                                                                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
                                                                            </svg>
                                                                            Lihat Chunk
                                                                        </button>
                                                                        <button
                                                                            onClick={() => {
                                                                                toggleDetail(doc, "logs");
                                                                                setOpenMenuId(null);
                                                                            }}
                                                                            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-[#1a6fa8] hover:bg-[#1a6fa8]/10"
                                                                        >
                                                                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.667 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.667m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25ZM6.75 12h.008v.008H6.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.008v.008H6.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
                                                                            </svg>
                                                                            Lihat Ingest Log
                                                                        </button>
                                                                        <button
                                                                            onClick={() => handleReIngest(doc)}
                                                                            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-[#1a6fa8] hover:bg-[#1a6fa8]/10"
                                                                        >
                                                                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                                                                            </svg>
                                                                            Re-ingest Dokumen
                                                                        </button>
                                                                        <div className="border-t border-gray-100"></div>
                                                                        <button
                                                                            onClick={() => {
                                                                                handleDelete(doc);
                                                                                setOpenMenuId(null);
                                                                            }}
                                                                            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                                                                        >
                                                                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                                                                            </svg>
                                                                            Hapus Dokumen
                                                                        </button>
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                                {detailRow}
                                            </Fragment>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="flex items-center justify-between border-t border-white/10 px-4 py-3">
                        <span className="text-sm text-[#1a3a52]/60">
                            Menampilkan {sortedDocs.length} dari {totalPages > 0 ? (currentPage * 10) : 0} dokumen
                        </span>
                        <div className="flex gap-1">
                            <button
                                disabled={currentPage === 1}
                                onClick={() => refreshDocs(currentPage - 1)}
                                className="rounded-lg px-3 py-1 text-sm transition-colors disabled:opacity-50 hover:bg-white/10"
                            >
                                ←
                            </button>
                            <span className="px-3 py-1 text-sm bg-[#1a6fa8]/20 rounded-lg text-[#1a6fa8]">
                                {currentPage} / {totalPages}
                            </span>
                            <button
                                disabled={currentPage === totalPages}
                                onClick={() => refreshDocs(currentPage + 1)}
                                className="rounded-lg px-3 py-1 text-sm transition-colors disabled:opacity-50 hover:bg-white/10"
                            >
                                →
                            </button>
                        </div>
                    </div>
                </div>

                {uploadError && (
                    <div className="rounded-xl border border-red-200 bg-red-50/90 p-3 text-xs text-red-700 shadow-sm animate-in fade-in duration-200">
                        {uploadError}
                    </div>
                )}
            </div>

            <UploadModal
                isOpen={isUploadOpenState}
                onClose={() => {
                    setIsUploadOpenState(false);
                    setUploadError(null);
                }}
                onUpload={submitUpload}
                isUploading={isUploading}
                uploadError={uploadError}
            />
        </div>
    );
}
