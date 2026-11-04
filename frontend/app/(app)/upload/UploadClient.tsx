"use client";

import { getUser } from "@/lib/auth";
import ManageSection from "./_components/ManageSection";

export default function UploadPage() {
    const user = getUser();
    const isAdmin = user?.role === "admin" && user.is_staff === true;

    if (!isAdmin) {
        return (
            <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[#1a3a52]/70">
                Anda tidak memiliki izin untuk mengakses halaman upload.
            </div>
        );
    }

    return <ManageSection />;
}
