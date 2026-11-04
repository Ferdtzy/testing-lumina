"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { clearAuth } from "@/lib/auth";

interface ShowMap {
    old: boolean;
    new: boolean;
    confirm: boolean;
}

interface PasswordStrength {
    score: number; // 0 to 4
    label: string;
    colorClass: string;
    bgClass: string;
}

function calculateStrength(password: string): PasswordStrength {
    if (!password) {
        return { score: 0, label: "Kosong", colorClass: "text-slate-400", bgClass: "bg-slate-300/40" };
    }

    let score = 0;
    if (password.length >= 8) score++;
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;

    switch (score) {
        case 1:
            return { score: 1, label: "Sangat Lemah", colorClass: "text-red-500", bgClass: "bg-red-500" };
        case 2:
            return { score: 2, label: "Cukup", colorClass: "text-amber-500", bgClass: "bg-amber-500" };
        case 3:
            return { score: 3, label: "Kuat", colorClass: "text-sky-600", bgClass: "bg-sky-500" };
        case 4:
            return { score: 4, label: "Sangat Kuat", colorClass: "text-emerald-600", bgClass: "bg-emerald-500" };
        default:
            return { score: 0, label: "Sangat Lemah", colorClass: "text-red-400", bgClass: "bg-red-400" };
    }
}

function EyeIcon() {
    return (
        <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
            />
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
        </svg>
    );
}

function EyeSlashIcon() {
    return (
        <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            viewBox="0 0 24 24"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
            />
        </svg>
    );
}

export default function PasswordClient() {
    const router = useRouter();
    const [oldPassword, setOldPassword] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [show, setShow] = useState<ShowMap>({ old: false, new: false, confirm: false });
    const [saving, setSaving] = useState(false);
    const [success, setSuccess] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const redirectTimerRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        return () => {
            if (redirectTimerRef.current) {
                clearTimeout(redirectTimerRef.current);
            }
        };
    }, []);

    const strength = calculateStrength(newPassword);

    const hasMinLength = newPassword.length >= 8;
    const isSameAsOld = newPassword.length > 0 && oldPassword.length > 0 && newPassword === oldPassword;
    const isConfirmEmpty = confirmPassword.length === 0;
    const isConfirmMatch = confirmPassword.length > 0 && newPassword === confirmPassword;
    const isConfirmMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

    const canSubmit =
        oldPassword.trim().length > 0 &&
        hasMinLength &&
        !isSameAsOld &&
        isConfirmMatch &&
        !saving &&
        !success;

    function toggle(field: keyof ShowMap) {
        setShow((prev) => ({ ...prev, [field]: !prev[field] }));
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setErrorMessage(null);

        if (!canSubmit) return;

        setSaving(true);
        try {
            await api.post("/auth/change-password/", {
                old_password: oldPassword,
                new_password: newPassword,
                confirm_password: confirmPassword,
            });

            clearAuth();
            setSuccess(true);
            setOldPassword("");
            setNewPassword("");
            setConfirmPassword("");

            redirectTimerRef.current = setTimeout(() => {
                router.replace("/login");
            }, 1500);
        } catch (err) {
            setSuccess(false);
            if (err instanceof ApiError) {
                setErrorMessage(err.message);
            } else if (err instanceof Error) {
                setErrorMessage(err.message);
            } else {
                setErrorMessage("Terjadi kesalahan pada sistem. Silakan coba lagi.");
            }
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="flex h-full w-full items-center justify-center p-4 md:p-6">
            {/* Card Container Max 640px */}
            <div className="glass-panel w-full max-w-[640px] overflow-hidden p-6 sm:p-8 md:p-10">
                {/* 1 & 5: Judul, Deskripsi, dan Tips Keamanan */}
                <div className="mb-6 md:mb-8 text-center sm:text-left">
                    <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#1a3a52]">
                        Ganti Password
                    </h1>
                    <p className="mt-1.5 text-xs sm:text-sm text-[#1a3a52]/75">
                        Perbarui password akun Anda untuk menjaga keamanan akun.
                    </p>
                    <p className="mt-1 text-[11px] sm:text-xs text-[#1a3a52]/50">
                        Gunakan password yang kuat dan jangan gunakan password yang sama dengan akun lain.
                    </p>
                </div>

                {/* Banner Error dari Server */}
                {errorMessage && (
                    <div
                        role="alert"
                        className="mb-6 flex items-start gap-2.5 rounded-2xl bg-rose-500/10 px-4 py-3 text-xs text-rose-600 ring-1 ring-rose-500/20"
                    >
                        <svg className="h-4 w-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <span>{errorMessage}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit} noValidate className="flex flex-col">
                    <div className="flex flex-col gap-5 sm:gap-6">
                        {/* Field 1: Password Lama */}
                        <div className="flex flex-col">
                            <label
                                htmlFor="old-password"
                                className="mb-1.5 text-xs sm:text-sm font-medium text-[#1a3a52]/80"
                            >
                                Password Lama
                            </label>
                            <div className="glass-inner flex items-center rounded-2xl px-4 py-3 sm:px-5 sm:py-3.5 transition-all duration-200 focus-within:ring-1 focus-within:ring-[#1a3a52]/30">
                                <input
                                    id="old-password"
                                    type={show.old ? "text" : "password"}
                                    value={oldPassword}
                                    onChange={(e) => setOldPassword(e.target.value)}
                                    placeholder="Masukkan password saat ini"
                                    autoComplete="current-password"
                                    disabled={saving || success}
                                    className="flex-1 border-none bg-transparent text-sm text-[#1a3a52]/85 outline-none placeholder:text-[#1a3a52]/40 disabled:cursor-not-allowed disabled:opacity-50"
                                />
                                <button
                                    type="button"
                                    onClick={() => toggle("old")}
                                    disabled={saving || success}
                                    aria-label={show.old ? "Sembunyikan password" : "Tampilkan password"}
                                    className="ml-2 text-[#1a3a52]/40 transition-colors hover:text-[#1a3a52]/80 disabled:cursor-not-allowed"
                                >
                                    {show.old ? <EyeSlashIcon /> : <EyeIcon />}
                                </button>
                            </div>
                        </div>

                        {/* Field 2: Password Baru */}
                        <div className="flex flex-col">
                            <label
                                htmlFor="new-password"
                                className="mb-1.5 text-xs sm:text-sm font-medium text-[#1a3a52]/80"
                            >
                                Password Baru
                            </label>
                            <div
                                className={`glass-inner flex items-center rounded-2xl px-4 py-3 sm:px-5 sm:py-3.5 transition-all duration-200 ${
                                    isSameAsOld || (newPassword.length > 0 && !hasMinLength)
                                        ? "ring-1 ring-red-400/50 bg-red-500/5"
                                        : "focus-within:ring-1 focus-within:ring-[#1a3a52]/30"
                                }`}
                            >
                                <input
                                    id="new-password"
                                    type={show.new ? "text" : "password"}
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    placeholder="Masukkan password baru"
                                    autoComplete="new-password"
                                    disabled={saving || success}
                                    aria-invalid={isSameAsOld || (newPassword.length > 0 && !hasMinLength)}
                                    aria-describedby="new-password-feedback"
                                    className="flex-1 border-none bg-transparent text-sm text-[#1a3a52]/85 outline-none placeholder:text-[#1a3a52]/40 disabled:cursor-not-allowed disabled:opacity-50"
                                />
                                <button
                                    type="button"
                                    onClick={() => toggle("new")}
                                    disabled={saving || success}
                                    aria-label={show.new ? "Sembunyikan password" : "Tampilkan password"}
                                    className="ml-2 text-[#1a3a52]/40 transition-colors hover:text-[#1a3a52]/80 disabled:cursor-not-allowed"
                                >
                                    {show.new ? <EyeSlashIcon /> : <EyeIcon />}
                                </button>
                            </div>

                            {/* 2 & 3: Helper Text, Strength Indicator & Realtime Validation */}
                            <div id="new-password-feedback" className="mt-1.5 px-1 flex flex-col gap-1">
                                {newPassword.length === 0 ? (
                                    <p className="text-[11px] sm:text-xs text-[#1a3a52]/50">
                                        Minimal 8 karakter · Gunakan kombinasi huruf, angka & simbol
                                    </p>
                                ) : (
                                    <>
                                        <div className="flex items-center justify-between text-[11px] sm:text-xs text-[#1a3a52]/70">
                                            <span>
                                                Kekuatan password: <strong className={strength.colorClass}>{strength.label}</strong>
                                            </span>
                                            <span>{newPassword.length} karakter</span>
                                        </div>
                                        <div className="mt-0.5 flex h-1.5 w-full gap-1 overflow-hidden rounded-full bg-white/30">
                                            {[1, 2, 3, 4].map((step) => (
                                                <div
                                                    key={step}
                                                    className={`h-full flex-1 rounded-full transition-all duration-300 ${
                                                        step <= strength.score ? strength.bgClass : "bg-transparent"
                                                    }`}
                                                />
                                            ))}
                                        </div>

                                        {/* Direct Field Error */}
                                        {!hasMinLength && (
                                            <p className="mt-0.5 text-xs text-rose-500" role="alert">
                                                ⚠ Password minimal terdiri dari 8 karakter
                                            </p>
                                        )}
                                        {isSameAsOld && (
                                            <p className="mt-0.5 text-xs text-amber-600" role="alert">
                                                ⚠ Password baru tidak boleh sama dengan password lama
                                            </p>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Field 3: Konfirmasi Password */}
                        <div className="flex flex-col">
                            <label
                                htmlFor="confirm-password"
                                className="mb-1.5 text-xs sm:text-sm font-medium text-[#1a3a52]/80"
                            >
                                Konfirmasi Password
                            </label>
                            <div
                                className={`glass-inner flex items-center rounded-2xl px-4 py-3 sm:px-5 sm:py-3.5 transition-all duration-200 ${
                                    isConfirmMismatch
                                        ? "ring-1 ring-red-400/50 bg-red-500/5"
                                        : isConfirmMatch
                                        ? "ring-1 ring-emerald-500/40 bg-emerald-500/5"
                                        : "focus-within:ring-1 focus-within:ring-[#1a3a52]/30"
                                }`}
                            >
                                <input
                                    id="confirm-password"
                                    type={show.confirm ? "text" : "password"}
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder="Ulangi password baru"
                                    autoComplete="new-password"
                                    disabled={saving || success}
                                    aria-invalid={isConfirmMismatch}
                                    aria-describedby={!isConfirmEmpty ? "confirm-feedback" : undefined}
                                    className="flex-1 border-none bg-transparent text-sm text-[#1a3a52]/85 outline-none placeholder:text-[#1a3a52]/40 disabled:cursor-not-allowed disabled:opacity-50"
                                />
                                <button
                                    type="button"
                                    onClick={() => toggle("confirm")}
                                    disabled={saving || success}
                                    aria-label={show.confirm ? "Sembunyikan password" : "Tampilkan password"}
                                    className="ml-2 text-[#1a3a52]/40 transition-colors hover:text-[#1a3a52]/80 disabled:cursor-not-allowed"
                                >
                                    {show.confirm ? <EyeSlashIcon /> : <EyeIcon />}
                                </button>
                            </div>

                            {/* Direct Field Validation Status */}
                            {!isConfirmEmpty && (
                                <div id="confirm-feedback" className="mt-1.5 px-1">
                                    {isConfirmMismatch ? (
                                        <p className="text-xs text-rose-500 flex items-center gap-1" role="alert">
                                            <span>⚠</span> Password tidak cocok
                                        </p>
                                    ) : (
                                        <p className="text-xs text-emerald-600 flex items-center gap-1">
                                            <span>✓</span> Password cocok
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* 4 & 8: Form Actions dengan tombol Simpan Perubahan Primer */}
                    <div className="mt-8 sm:mt-9 flex items-center justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={() => {
                                if (window.history.length > 1) {
                                    router.back();
                                } else {
                                    router.push("/");
                                }
                            }}
                            disabled={saving || success}
                            className="glass-inner rounded-2xl px-5 py-2.5 sm:px-6 sm:py-2.5 text-xs sm:text-sm font-medium text-[#1a3a52]/75 transition-all hover:bg-white/30 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                            Batal
                        </button>
                        <button
                            type="submit"
                            disabled={!canSubmit}
                            className={`flex items-center gap-2 rounded-2xl px-6 py-2.5 sm:px-7 sm:py-2.5 text-xs sm:text-sm font-semibold transition-all duration-200 shadow-sm ${
                                canSubmit
                                    ? "bg-[#1a6fa8] text-white shadow-md shadow-[#1a6fa8]/20 hover:bg-[#155a8a] active:scale-[0.98] cursor-pointer"
                                    : "glass-inner text-[#1a3a52]/40 opacity-50 cursor-not-allowed border-white/20"
                            }`}
                        >
                            {saving && (
                                <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                            )}
                            <span>{saving ? "Menyimpan…" : "Simpan Perubahan"}</span>
                        </button>
                    </div>
                </form>
            </div>

            {/* 9: Feedback Status Toast Setelah Berhasil */}
            {success && (
                <div
                    role="status"
                    aria-live="polite"
                    className="glass-panel fixed bottom-6 right-6 z-50 flex items-start gap-3 rounded-2xl bg-white/80 p-4 text-emerald-800 shadow-xl backdrop-blur-xl ring-1 ring-emerald-500/30 transition-all duration-300 animate-in fade-in slide-in-from-bottom-3"
                >
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-emerald-900">Password berhasil diubah</p>
                        <p className="text-xs text-emerald-700/80">Password akun Anda telah diperbarui. Mengalihkan ke login…</p>
                    </div>
                </div>
            )}
        </div>
    );
}