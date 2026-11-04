"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import Markdown from "@/components/Markdown";
import { api } from "@/lib/api";

interface QueryDetail {
    id: number;
    query_text: string;
    query_title: string;
    display_title: string;
    status: string;
    response_time_ms: number | null;
    created_at: string;
}

interface AnswerDetail {
    id: number;
    query: number;
    answer_text: string;
    sources: unknown[] | null;
    created_at: string;
}

interface HistoryItem {
    id: number;
    query: number;
    query_detail: QueryDetail;
    answer: number | null;
    answer_detail: AnswerDetail | null;
}

interface Paginated<T> {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
}

function formatDate(iso: string): string {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("id-ID", {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(d);
}

function relativeTime(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "baru saja";
    if (mins < 60) return `${mins} menit lalu`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} jam lalu`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} hari lalu`;
    return formatDate(iso);
}

export default function HistoryPage() {
    const [items, setItems] = useState<HistoryItem[]>([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [openIds, setOpenIds] = useState<Set<number>>(new Set());

    useEffect(() => {
        const abortController = new AbortController();
        api
            .get<Paginated<HistoryItem>>("/history/", { signal: abortController.signal })
            .then((data) => {
                if (!abortController.signal.aborted) {
                    setItems(Array.isArray(data?.results) ? data.results : []);
                }
            })
            .catch((err) =>
                !abortController.signal.aborted && setError(
                    err instanceof Error ? err.message : "Gagal memuat riwayat chat.",
                ),
            )
            .finally(() => {
                if (!abortController.signal.aborted) setLoading(false);
            });
        return () => abortController.abort();
    }, []);

    const filtered = items.filter((item) =>
        (item.query_detail?.display_title || item.query_detail?.query_text || "")
            .toLowerCase()
            .includes(search.toLowerCase()),
    );

    return (
        <div className="glass-panel flex h-full flex-col overflow-hidden">
            <div className="shrink-0 px-5 pb-4 pt-5">
                <h3 className="mb-4 text-lg font-semibold leading-tight text-[#1a3a52]">
                    Riwayat Pertanyaan
                </h3>

                <div className="glass-inner flex items-center gap-3 rounded-2xl px-4 py-3">
                    <svg
                        className="h-4 w-4 shrink-0 text-[#1a3a52]/60"
                        fill="currentColor"
                        viewBox="0 0 32 32"
                    >
                        <path d="M31.707 30.282l-9.717-9.776c1.811-2.169 2.902-4.96 2.902-8.007 0-6.904-5.596-12.5-12.5-12.5s-12.5 5.596-12.5 12.5 5.596 12.5 12.5 12.5c3.136 0 6.002-1.158 8.197-3.067l9.703 9.764c0.39 0.39 1.024 0.39 1.415 0s0.39-1.023 0-1.415zM12.393 23.016c-5.808 0-10.517-4.709-10.517-10.517s4.708-10.517 10.517-10.517c5.808 0 10.516 4.708 10.516 10.517s-4.709 10.517-10.517 10.517z" />
                    </svg>
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Cari pertanyaan..."
                        className="flex-1 border-none bg-transparent text-sm text-[#1a3a52]/70 outline-none placeholder:text-[#1a3a52]/60"
                    />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 pb-24 md:pb-5">
                {loading ? (
                    <div className="glass-inner mt-4 rounded-xl px-4 py-3 text-sm text-[#1a3a52]/70">
                        Memuat riwayat…
                    </div>
                ) : error ? (
                    <div className="mt-4 rounded-xl border border-red-300/60 bg-red-50/80 px-4 py-3 text-sm text-red-600">
                        {error}
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-center">
                        <p className="text-sm text-[#1a3a52]/50">
                            {items.length === 0 ? "Belum ada riwayat pertanyaan." : "Tidak ditemukan pertanyaan yang cocok."}
                        </p>
                        {items.length === 0 && (
                            <Link href="/" className="mt-3 text-sm text-[#1a6fa8] hover:underline">
                                Mulai chat sekarang
                            </Link>
                        )}
                    </div>
                ) : (
                    <div className="flex flex-col gap-1">
                        {filtered.map((item) => (
                            <details key={item.id} className="group" onToggle={(event) => {
                                const isOpen = event.currentTarget.open;
                                setOpenIds((previous) => {
                                    const next = new Set(previous);
                                    if (isOpen) next.add(item.id);
                                    else next.delete(item.id);
                                    return next;
                                });
                            }}>
                                <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl px-4 py-3.5 transition-all hover:bg-white/20">
                                    <div className="min-w-0 flex-1">
                                        <p className="truncate text-sm text-[#1a3a52]/80">
                                            {item.query_detail?.display_title || item.query_detail?.query_text || `Riwayat #${item.id}`}
                                        </p>
                                        <p className="mt-0.5 text-xs text-[#1a3a52]/40">
                                            {item.query_detail?.created_at && relativeTime(item.query_detail.created_at)}
                                            {item.query_detail?.status === "answered" && (
                                                <span className="ml-1 text-green-600">· Terjawab</span>
                                            )}
                                            {item.query_detail?.status === "failed" && (
                                                <span className="ml-1 text-rose-500">· Gagal</span>
                                            )}
                                            {item.query_detail?.status === "pending" && (
                                                <span className="ml-1 text-yellow-600">· Pending</span>
                                            )}
                                        </p>
                                    </div>
                                    <svg
                                        className="h-3.5 w-3.5 shrink-0 text-[#1a3a52]/20 opacity-0 transition-opacity group-open:rotate-90 group-hover:opacity-100"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth={2}
                                        viewBox="0 0 24 24"
                                    >
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                                    </svg>
                                </summary>
                                {openIds.has(item.id) && <div className="mb-2 ml-5 border-l border-white/25 pl-4">
                                    <p className="mb-1 mt-2 text-xs font-semibold text-[#1a3a52]/50">Pertanyaan</p>
                                    <p className="text-sm text-[#1a3a52]/90">{item.query_detail?.query_text || ""}</p>
                                    {item.answer_detail && (
                                        <>
                                            <p className="mb-1 mt-3 text-xs font-semibold text-[#1a3a52]/50">Jawaban</p>
                                            <Markdown content={item.answer_detail.answer_text} />
                                        </>
                                    )}
                                </div>}
                            </details>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
