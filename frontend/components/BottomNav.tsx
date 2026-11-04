"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { getUser } from "@/lib/auth";

export default function BottomNav() {
    const pathname = usePathname();
    const user = getUser();
    const isAdmin = user?.role === "admin" && user?.is_staff === true;

    const isActive = (path: string) => {
        if (path === "/") return pathname === "/";
        return pathname.startsWith(path);
    };

    return (
        <nav id="bottom-nav" className="md:hidden">
            {/* New Chat */}
            <Link
                href="/"
                className={`flex flex-col items-center gap-1 rounded-xl px-3 py-1 transition-all ${
                    isActive("/")
                        ? "text-[#1a6fa8]"
                        : "text-[#1a3a52]/70 hover:text-[#1a3a52]"
                }`}
            >
                <svg
                    className="h-5 w-5 opacity-70"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
                </svg>
                <span className="text-[10px] font-medium">Chat</span>
            </Link>

            {/* Upload — admin only */}
            {isAdmin && (
                <Link
                    href="/upload"
                    className={`flex flex-col items-center gap-1 rounded-xl px-3 py-1 transition-all ${
                        isActive("/upload")
                            ? "text-[#1a6fa8]"
                            : "text-[#1a3a52]/70 hover:text-[#1a3a52]"
                    }`}
                >
                    <svg
                        className="h-5 w-5 opacity-70"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                    </svg>
                    <span className="text-[10px] font-medium">Upload</span>
                </Link>
            )}
        </nav>
    );
}
