"use client";

import { useEffect, useRef, useState, useCallback, useMemo, type FormEvent, type KeyboardEvent } from "react";
import Image from "next/image";

import { api } from "@/lib/api";
import { getUser } from "@/lib/auth";

interface Source {
    source: string;
    page: number | null;
    score: number | null;
    excerpt: string;
    source_type?: "document_text" | "ocr" | "vision" | null;
    image_ref?: string | null;
    ocr_confidence?: number | null;
}

interface AskResponse {
    success: boolean;
    query_id: number;
    answer_id: number | null;
    answer: string;
    response_time_ms: number;
    sources: Source[];
    conversation_id?: number;
}

interface ChatMessage {
    id: number;
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
    responseTimeMs?: number;
}

interface DocumentItem {
    id: number;
    document_name: string;
    size_human: string;
    status: string;
}

interface Paginated<T> {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
}

export default function DashboardPage() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [question, setQuestion] = useState("");
    const [loading, setLoading] = useState(false);
    const [documents, setDocuments] = useState<DocumentItem[]>([]);
    const [username, setUsername] = useState("Pengguna");
    const [error, setError] = useState<string | null>(null);
    const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const idCounter = useRef(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        const user = getUser();
        if (user?.username) setUsername(user.username);

        const savedConvId = localStorage.getItem("activeConversationId");
        if (savedConvId) {
            setActiveConversationId(Number(savedConvId));
        }

        api
            .get<Paginated<DocumentItem>>("/documents/")
            .then((data) => setDocuments(data.results))
            .catch(() => setDocuments([]));
    }, []);

    useEffect(() => {
        function handleNewChat() {
            setMessages([]);
            setQuestion("");
            setError(null);
            setLoading(false);
            setActiveConversationId(null);
            localStorage.removeItem("activeConversationId");
            idCounter.current = 0;
            if (textareaRef.current) {
                textareaRef.current.style.height = "auto";
            }
        }

        function handleOpenConversation(e: Event) {
            const detail = (e as CustomEvent<{ id: number }>).detail;
            if (!detail?.id) return;

            handleNewChat();
            setLoading(true);

            api
                .get<{
                    conversation_id: number;
                    messages: {
                        id: number;
                        role: "user" | "assistant";
                        content: string;
                        created_at: string;
                    }[];
                }>(`/conversations/${detail.id}/messages/`, { timeout: 10000 })
                .then((data) => {
                    setActiveConversationId(data.conversation_id);
                    localStorage.setItem("activeConversationId", String(data.conversation_id));
                    const loadedMessages = data.messages.map((msg) => ({
                        id: ++idCounter.current,
                        role: msg.role as "user" | "assistant",
                        content: msg.content,
                    }));
                    setMessages(loadedMessages);
                })
                .catch(() => {
                    setError("Gagal memuat percakapan.");
                })
                .finally(() => setLoading(false));
        }

        window.addEventListener("lumina:new-chat", handleNewChat);
        window.addEventListener("lumina:open-conversation", handleOpenConversation);
        return () => {
            window.removeEventListener("lumina:new-chat", handleNewChat);
            window.removeEventListener("lumina:open-conversation", handleOpenConversation);
        };
    }, []);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, loading]);

    function autoResize(el: HTMLTextAreaElement) {
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }

    async function sendMessage() {
        const text = question.trim();
        if (!text || loading) return;

        setError(null);
        const userMessage: ChatMessage = {
            id: ++idCounter.current,
            role: "user",
            content: text,
        };
        setMessages((prev) => [...prev, userMessage]);
        setQuestion("");
        setLoading(true);

        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
        }

        try {
            const payload: { question: string; conversation_id?: number } = { question: text };

            if (activeConversationId) {
                payload.conversation_id = activeConversationId;
            }

            const data = await api.post<AskResponse>("/ask/", payload, { timeout: 120_000 });

            if (data.conversation_id && !activeConversationId) {
                setActiveConversationId(data.conversation_id);
                localStorage.setItem("activeConversationId", String(data.conversation_id));
                window.dispatchEvent(new CustomEvent("lumina:conversation-created", { detail: { id: data.conversation_id, title: text.split(" ").slice(0, 8).join(" ") + (text.length > 8 ? "…" : "") } }));
            }

            const assistantMessage: ChatMessage = {
                id: ++idCounter.current,
                role: "assistant",
                content: data.answer,
                sources: data.sources ?? [],
                responseTimeMs: data.response_time_ms,
            };
            setMessages((prev) => [...prev, assistantMessage]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    id: ++idCounter.current,
                    role: "assistant",
                    content:
                        err instanceof Error
                            ? `⚠️ ${err.message}`
                            : "⚠️ Terjadi kesalahan saat memproses pertanyaan.",
                },
            ]);
        } finally {
            setLoading(false);
        }
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        void sendMessage();
    }

    function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void sendMessage();
        }
    }

    function copyText(text: string) {
        navigator.clipboard.writeText(text);
    }

    const inputArea = (
        <>
            {error && <p className="mb-1 text-xs text-red-500">{error}</p>}
            <form onSubmit={handleSubmit} className="flex items-center gap-2.5 rounded-3xl border border-white/50 bg-white/65 px-5 py-2 shadow-[0_8px_32px_rgba(31,38,135,0.1)] backdrop-blur-[20px] transition-all duration-300 focus-within:border-[#3b82f6]/40 focus-within:shadow-[0_8px_32px_rgba(59,130,246,0.15)]">
                <textarea
                    ref={textareaRef}
                    value={question}
                    onChange={(e) => {
                        setQuestion(e.target.value);
                        autoResize(e.target);
                    }}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    placeholder="Ketik pertanyaanmu..."
                    spellCheck={false}
                    autoComplete="off"
                    disabled={loading}
                    className="max-h-[120px] min-h-[36px] flex-1 resize-none border-none bg-transparent py-2 text-sm text-[#1e3a8a] placeholder-[#60a5fa] outline-none disabled:opacity-50"
                />
                <div className="flex shrink-0 items-center gap-1.5">
                    <button type="button" title="Lampirkan file" className="flex h-9 w-9 items-center justify-center rounded-full text-[#60a5fa] transition-colors hover:bg-[#3b82f6]/10 hover:text-[#2563eb]">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                    </button>
                    <button type="button" title="Input suara" className="flex h-9 w-9 items-center justify-center rounded-full text-[#60a5fa] transition-colors hover:bg-[#3b82f6]/10 hover:text-[#2563eb]">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" /></svg>
                    </button>
                    <button type="submit" disabled={loading || !question.trim()} className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[#3b82f6] to-[#1d4ed8] text-white shadow-[0_4px_14px_rgba(37,99,235,0.3)] transition-all duration-300 hover:scale-105 hover:shadow-[0_6px_20px_rgba(37,99,235,0.45)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 disabled:hover:shadow-[0_4px_14px_rgba(37,99,235,0.3)]" aria-label="Kirim">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
                    </button>
                </div>
            </form>
            {messages.length > 0 && (
                <p className="mt-2 text-center text-xs text-[#1e3a8a]">
                    Lumina dapat membuat kesalahan. Pastikan untuk memeriksa informasi penting.
                </p>
            )}
        </>
    );

    return (
        <div className="flex h-full flex-col overflow-hidden">
            {/* Chat area */}
            <div ref={scrollRef} className="flex flex-1 flex-col overflow-y-auto">
                {messages.length === 0 && (
                    <div className="flex flex-1 flex-col items-center justify-center px-10 py-10 text-center">
                        <div className="flex h-[72px] w-[72px] items-center justify-center">
                            <Image src="/images/icons/Logo.png" width={72} height={72} className="h-full w-full object-contain mix-blend-multiply" alt="Lumina" />
                        </div>
                        <h1 className="mb-2 text-[28px] font-bold tracking-tight text-[#1e3a8a]">
                            Halo! Saya <span className="text-[#3b82f6]">Lumina</span>
                        </h1>
                        <p className="mb-9 max-w-[440px] text-[15px] leading-relaxed text-[#1e3a8a]/80">
                            Asisten akademikmu. Ajukan pertanyaan dan aku akan menjawabnya sesuai pengetahuanku.
                        </p>
                        {documents.length === 0 && (
                            <p className="mb-6 max-w-md text-xs text-[#60a5fa]/70">
                                Belum ada dokumen terindeks. Hubungi admin untuk mengunggah dokumen sebelum mengajukan pertanyaan.
                            </p>
                        )}
                        <div className="mx-auto w-full max-w-[820px]">
                            {inputArea}
                        </div>
                    </div>
                )}

                {messages.length > 0 && (
                    <div className="mx-auto flex w-full max-w-[820px] flex-col gap-5 px-5 pt-6 pb-2.5">
                        {messages.map((msg) => (
                            <div key={msg.id} className={`flex gap-3.5 ${msg.role === "user" ? "flex-row-reverse text-right" : ""}`}>
                                {msg.role === "assistant" ? (
                                    <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[#1d4ed8]">
                                        <Image src="/images/icons/Logo.png" width={18} height={18} className="h-[18px] w-[18px]" alt="Lumina" />
                                    </div>
                                ) : (
                                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#60a5fa] to-[#2563eb] text-[14px] font-semibold text-white">
                                        {username.slice(0, 1).toUpperCase()}
                                    </div>
                                )}
                                <div className={`min-w-0 flex-1 ${msg.role === "user" ? "flex flex-col items-end" : ""}`}>
                                    <div className="mb-1 text-[13px] font-semibold text-[#1e3a8a]">
                                        {msg.role === "user" ? username : "Lumina"}
                                    </div>
                                    {msg.role === "user" ? (
                                        <div className="inline-block rounded-[16px_4px_16px_16px] border border-[#3b82f6]/15 bg-[#3b82f6]/10 px-4 py-3 text-left text-[14px] leading-[1.7] text-[#1e3a8a]">
                                            <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                                {msg.content}
                                            </span>
                                        </div>
                                    ) : (
                                        <div>
                                            <p className="whitespace-pre-wrap break-words text-[14px] leading-[1.7] text-[#1e3a8a]">
                                                {msg.content}
                                            </p>
                                            {msg.sources && msg.sources.length > 0 && (
                                                <details className="mt-3">
                                                    <summary className="cursor-pointer text-xs font-medium text-[#2563eb]">
                                                        Lihat {msg.sources.length} sumber
                                                    </summary>
                                                    <ul className="mt-2 space-y-2">
                                                        {msg.sources.map((source, idx) => (
                                                            <li
                                                                key={idx}
                                                                className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs"
                                                            >
                                                                <span className="font-semibold">{source.source}</span>
                                                                <span className="ml-2 text-slate-500">
                                                                    {source.page != null && `Hal. ${source.page} · `}
                                                                    {source.source_type === "ocr"
                                                                        ? "OCR"
                                                                        : source.source_type === "vision"
                                                                          ? "Gemini Vision"
                                                                          : source.source_type === "document_text"
                                                                            ? "Teks dokumen"
                                                                            : "Asal belum tercatat"}
                                                                    {source.image_ref && ` · ${source.image_ref}`}
                                                                    {source.source_type === "ocr" && source.ocr_confidence != null &&
                                                                        ` · keyakinan OCR ${Math.round(source.ocr_confidence * 100)}%`}
                                                                </span>
                                                                <p className="mt-1 line-clamp-3 text-slate-600">
                                                                    {source.excerpt}
                                                                </p>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </details>
                                            )}
                                            <div className="mt-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 [&:hover]:opacity-100">
                                                <button
                                                    type="button"
                                                    title="Salin"
                                                    onClick={() => copyText(msg.content)}
                                                    className="rounded-md p-1.5 text-[#60a5fa] transition-colors hover:bg-[#3b82f6]/10 hover:text-[#2563eb]"
                                                >
                                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-[15px] w-[15px]">
                                                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                                                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                                                    </svg>
                                                </button>
                                                {msg.responseTimeMs !== undefined && (
                                                    <span className="ml-1 self-center text-[10px] text-[#60a5fa]/60">
                                                        {(msg.responseTimeMs / 1000).toFixed(2)} s
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}

                        {loading && (
                            <div className="flex gap-3.5">
                                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#1d4ed8] overflow-hidden">
                                    <Image src="/images/icons/Logo.png" width={18} height={18} className="h-[18px] w-[18px]" alt="Lumina" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="mb-1 text-[13px] font-semibold text-[#1e3a8a]">Lumina</div>
                                    <div className="flex gap-[5px] py-2">
                                        <span className="typing-dot h-2 w-2 rounded-full bg-[#60a5fa]" />
                                        <span className="typing-dot h-2 w-2 rounded-full bg-[#60a5fa]" />
                                        <span className="typing-dot h-2 w-2 rounded-full bg-[#60a5fa]" />
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {messages.length > 0 && <div className="shrink-0 px-5 pb-5 pt-4"><div className="mx-auto w-full max-w-[820px]">{inputArea}</div></div>}
        </div>
    );
}
