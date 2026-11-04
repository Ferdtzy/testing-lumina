"use client";

import { useEffect, useState, useRef, useMemo, Fragment } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import Image from "next/image";

import { api } from "@/lib/api";
import { clearAuth, getUser } from "@/lib/auth";

interface SidebarProps {
    isOpen: boolean;
    onClose: () => void;
}

interface ConversationResponse {
    id: number;
    title?: string;
    created_at?: string;
    createdAt?: string;
    query_detail?: { created_at?: string };
}

interface ConversationItem {
    id: number;
    title: string;
    createdAt: string;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
    const router = useRouter();
    const pathname = usePathname();
    const user = getUser();
    const isAdmin = user?.role === "admin" && user?.is_staff === true;
    const [accountOpen, setAccountOpen] = useState(false);
    const [conversations, setConversations] = useState<
        ConversationItem[]
    >([]);
    const [newConversationId, setNewConversationId] = useState<number | null>(null);
    const [searchHistory, setSearchHistory] = useState("");
    const [searchResults, setSearchResults] = useState<
        ConversationItem[]
    >([]);
    const newChatRef = useRef<HTMLAnchorElement>(null);

    const fetchConversations = async (q: string = "") => {
        try {
            const url = q 
                ? `/conversations/search/?q=${encodeURIComponent(q)}`
                : "/conversations/";
            
            const data = await api.get<{ results: ConversationResponse[] }>(url);
            const newConversations = Array.isArray(data?.results) ? data.results : [];
            
            if (!q) {
                const mapped = newConversations.slice(0, 10).map((c) => ({
                    id: c.id,
                    title: c.title || `Percakapan #${c.id}`,
                    createdAt:
                        c.query_detail?.created_at ||
                        c.created_at ||
                        new Date().toISOString(),
                }));
                setConversations(mapped);
            } else {
                const mapped = newConversations.map((c) => ({
                    id: c.id,
                    title: c.title || `Percakapan #${c.id}`,
                    createdAt: c.created_at || c.createdAt || new Date().toISOString(),
                }));
                setSearchResults(mapped);
            }
        } catch {
            if (!q) setConversations([]);
        }
    };

    useEffect(() => {
        const timer = window.setTimeout(() => {
            void fetchConversations();
        }, 0);

        function handleConversationCreated(e: Event) {
            const detail = (e as CustomEvent<{ id: number; title: string }>).detail;
            if (detail?.id) {
                setNewConversationId(detail.id);
                fetchConversations();
            }
        }

        window.addEventListener("lumina:conversation-created", handleConversationCreated);
        return () => {
            window.clearTimeout(timer);
            window.removeEventListener("lumina:conversation-created", handleConversationCreated);
        };
    }, []);

    useEffect(() => {
        if (searchHistory.trim()) {
            const timer = setTimeout(() => {
                fetchConversations(searchHistory);
            }, 300);
            return () => clearTimeout(timer);
        } else {
            const timer = window.setTimeout(() => {
                void fetchConversations();
            }, 0);
            return () => window.clearTimeout(timer);
        }
    }, [searchHistory]);

    function handleNewChat() {
        setNewConversationId(null);
        window.dispatchEvent(new Event("lumina:new-chat"));
        router.push("/");
        onClose();
    }

    function handleAccountToggle() {
        setAccountOpen((open) => !open);
    }

    function handleLogout() {
        clearAuth();
        setAccountOpen(false);
        router.push("/login");
        onClose();
    }

    function handleChangePassword() {
        setAccountOpen(false);
        router.push("/change-password");
        onClose();
    }

    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart);
    yesterdayStart.setDate(yesterdayStart.getDate() - 1);

    function getDateGroup(iso: string): "today" | "yesterday" | "older" {
        const date = new Date(iso);
        if (date >= todayStart) return "today";
        if (date >= yesterdayStart) return "yesterday";
        return "older";
    }

    const groupedConversations = {
        today: conversations.filter((c) => getDateGroup(c.createdAt) === "today"),
        yesterday: conversations.filter((c) => getDateGroup(c.createdAt) === "yesterday"),
        older: conversations.filter((c) => getDateGroup(c.createdAt) === "older"),
    };

    const renderConversations = useMemo(() => {
        if (searchHistory.trim()) {
            if (searchResults.length === 0) {
                return (
                    <span className="px-3 py-2 text-xs italic text-blue-400/70">
                        Tidak ada percakapan ditemukan
                    </span>
                );
            }
            return searchResults.map((c) => (
                <button
                    key={c.id}
                    onClick={() => {
                        window.dispatchEvent(new CustomEvent("lumina:open-conversation", { detail: { id: c.id } }));
                        onClose();
                    }}
                    className="flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-blue-950/70 transition-all hover:bg-white/55 hover:text-blue-700 w-full text-left"
                    title={c.title}
                >
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-300/80" />
                    <span className="truncate">{c.title}</span>
                </button>
            ));
        }
        
        const allConversations = [
            ...groupedConversations.today.map(c => ({...c, group: "today"})),
            ...groupedConversations.yesterday.map(c => ({...c, group: "yesterday"})),
            ...groupedConversations.older.map(c => ({...c, group: "older"})),
        ];
        
        if (allConversations.length === 0) {
            return <span className="px-3 py-2 text-xs italic text-blue-400/70">Belum ada riwayat</span>;
        }
        
        const sections: Record<string, Array<ConversationItem & { group: string }>> = {
            today: allConversations.filter(c => c.group === "today"),
            yesterday: allConversations.filter(c => c.group === "yesterday"),
            older: allConversations.filter(c => c.group === "older"),
        };
        
        return Object.entries(sections).map(([group, items]) => {
            if (items.length === 0) return null;
            return (
                <Fragment key={group}>
                    <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-blue-900/80">
                        {group === "today" ? "Hari ini" : group === "yesterday" ? "Kemarin" : "Lebih lama"}
                    </div>
                    {items.map((c) => (
                        <button
                            key={c.id}
                            onClick={() => {
                                window.dispatchEvent(new CustomEvent("lumina:open-conversation", { detail: { id: c.id } }));
                                onClose();
                            }}
                            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-blue-950/70 transition-all hover:bg-white/55 hover:text-blue-700 w-full text-left ${
                                c.id === newConversationId ? "animate-pulse bg-blue-50/50" : ""
                            }`}
                            title={c.title}
                        >
                            <span className="h-1.5 w-1.5 rounded-full bg-blue-300/80" />
                            <span className="truncate">{c.title}</span>
                        </button>
                    ))}
                </Fragment>
            );
        });
    }, [searchHistory, searchResults, groupedConversations, newConversationId, onClose]);

    return (
        <aside
            id="app-sidebar"
            className={`fixed inset-y-0 left-0 z-50 flex h-full w-[280px] -translate-x-full flex-col border-r border-white/40 bg-white/65 shadow-[0_8px_32px_rgba(31,38,135,0.1)] backdrop-blur-xl transition-transform duration-300 md:static md:w-72 md:translate-x-0 ${
                isOpen ? "translate-x-0" : "-translate-x-full"
            }`}
        >
            <div className="flex items-center justify-between border-b border-white/40 px-4 py-5">
                <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center">
                        <Image
                            src="/images/icons/Logo.png"
                            width={40}
                            height={40}
                            className="h-full w-full object-contain"
                            alt="Logo"
                        />
                    </div>
                    <div className="leading-none">
                        <p className="text-[18px] font-bold tracking-tight text-blue-900">
                            Lumi<span className="text-blue-500">na</span>
                        </p>
                        <p className="mt-1 text-[11px] text-blue-400">Assistant</p>
                    </div>
                </div>
            </div>

            <div className="px-3 py-2">
                <Link
                    ref={newChatRef}
                    href="/"
                    onClick={handleNewChat}
                    className={`flex items-center gap-3 rounded-xl px-4 py-2 text-sm font-medium text-blue-700 transition-all hover:bg-white/80`}
                >
                    <span className="flex h-5 w-5 items-center justify-center">
                        <Image
                            src="/images/icons/NewChatIcon.png"
                            width={18}
                            height={18}
                            className="h-4.5 w-4.5 opacity-80"
                            alt=""
                        />
                    </span>
                    <span>New Chat</span>
                </Link>
            </div>

            <div className="flex-1 overflow-y-auto px-3 pb-3">
                {isAdmin && (
                    <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-blue-900">
                        Dokumen
                    </div>
                )}

                {isAdmin && (
                    <Link
                        href="/upload"
                        onClick={onClose}
                        className={`flex items-center gap-3 rounded-xl px-4 py-2 text-sm font-medium text-blue-700 transition-all hover:bg-white/55 ${
                            pathname === "/upload" ? "bg-blue-50/80" : ""
                        }`}
                    >
                        <Image
                            src="/images/icons/UploadIcon.png"
                            width={18}
                            height={18}
                            className="h-4.5 w-4.5 opacity-75"
                            alt=""
                        />
                        <span>Upload Dokumen</span>
                    </Link>
                )}

                <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-blue-900">
                    Riwayat Chat
                </div>
                <div className="px-3 py-2">
                    <div className="glass-inner flex items-center gap-2 rounded-xl px-3 py-2">
                        <svg className="h-4 w-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        <input
                            value={searchHistory}
                            onChange={(e) => setSearchHistory(e.target.value)}
                            placeholder="Cari riwayat..."
                            className="flex-1 bg-transparent text-sm outline-none"
                        />
                        {searchHistory && (
                            <button onClick={() => setSearchHistory("")}>
                                <svg className="h-4 w-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        )}
                    </div>
                </div>
                <div className="flex flex-col gap-1 pl-4">
                    {renderConversations}
                </div>
            </div>

            <div className="relative border-t border-white/40 px-4 py-4">
                {accountOpen && (
                    <div className="absolute bottom-[76px] left-4 right-4 z-20 overflow-hidden rounded-xl border border-white/50 bg-white/80 p-1 shadow-[0_12px_32px_rgba(37,99,235,0.18)] backdrop-blur-xl">
                        <button
                            type="button"
                            onClick={handleChangePassword}
                            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium text-blue-700 transition-all hover:bg-blue-50/80 hover:text-blue-900"
                        >
                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-600">
                                CP
                            </span>
                            <span>Change Password</span>
                        </button>
                        <button
                            type="button"
                            onClick={handleLogout}
                            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium text-blue-700 transition-all hover:bg-blue-50/80 hover:text-blue-900"
                        >
                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-600">
                                LO
                            </span>
                            <span>Logout</span>
                        </button>
                    </div>
                )}
                <button
                    type="button"
                    onClick={handleAccountToggle}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-white/55"
                    aria-expanded={accountOpen}
                >
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-sm font-semibold text-white shadow-[0_4px_14px_rgba(37,99,235,0.25)]">
                        {user?.username?.slice(0, 1).toUpperCase() || "U"}
                    </span>
                    <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-blue-950">
                            {user?.username || "Pengguna"}
                        </span>
                        <span className="block truncate text-[11px] text-blue-400 capitalize">
                            {user?.role || "member"}
                        </span>
                    </span>
                    <span className={`text-sm text-blue-400 transition-transform ${accountOpen ? "rotate-180" : ""}`}>
                        ˅
                    </span>
                </button>
            </div>
        </aside>
    );
}
