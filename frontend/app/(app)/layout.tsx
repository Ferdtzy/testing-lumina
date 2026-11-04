"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import { api, ApiError } from "@/lib/api";
import { clearAuth, getToken, setUser, type AuthUser } from "@/lib/auth";

export default function AppLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const router = useRouter();
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [ready, setReady] = useState(false);

    useEffect(() => {
        const token = getToken();
        if (!token) {
            router.replace("/login");
            return;
        }

        // Validasi token ke backend; bila tidak sah, arahkan ke login.
        api
            .get<AuthUser>("/auth/me/")
            .then((user) => {
                setUser(user);
                setReady(true);
            })
            .catch((err) => {
                if (err instanceof ApiError && err.status === 401) {
                    clearAuth();
                    router.replace("/login");
                } else {
                    // Token ada tapi jaringan/backend bermasalah — tetap tampil, data
                    // akan gagal di-fetch bila memang tidak berizin.
                    setReady(true);
                }
            });
    }, [router]);

    if (!ready) {
        return (
            <div className="flex h-full items-center justify-center">
                <div className="glass-inner rounded-xl px-6 py-4 text-sm text-[#1a3a52]/70">
                    Memuat…
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-full">
            <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

            <div
                id="main-content"
                className="flex min-w-0 flex-1 flex-col gap-2 md:gap-3"
            >
                <main className="min-h-0 flex-1 overflow-visible">{children}</main>
            </div>

            <BottomNav />
        </div>
    );
}