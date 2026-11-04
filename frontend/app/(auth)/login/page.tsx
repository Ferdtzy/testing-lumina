"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { setAuth, type AuthUser } from "@/lib/auth";

interface LoginResponse {
    token: string;
    user: AuthUser;
}

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [rememberMe, setRememberMe] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);

        if (!email.trim() || !password) {
            setError("Email dan kata sandi wajib diisi.");
            return;
        }

        setLoading(true);
        try {
            const data = await api.post<LoginResponse>("/auth/login/", {
                email: email.trim(),
                password,
            });
            setAuth(data.token, data.user);
            router.replace("/");
            router.refresh();
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "Gagal masuk. Silakan periksa kembali email dan kata sandi Anda.",
            );
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="flex h-screen h-[100dvh] max-h-screen w-full flex-col lg:flex-row bg-[#ebf4fa] text-[#1a3a52] overflow-hidden">
            {/* ── Left Panel (50% Desktop, Hidden on Mobile) ──────────────────── */}
            <div className="relative hidden w-full h-full flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0d346c] via-[#1a5db4] to-[#2b7de9] p-6 lg:flex lg:w-1/2 xl:p-10 text-white">
                {/* Decorative Glowing Orbs */}
                <div className="pointer-events-none absolute -left-20 -top-20 h-80 w-80 rounded-full bg-cyan-400/25 blur-3xl" />
                <div className="pointer-events-none absolute -right-24 top-1/3 h-96 w-96 rounded-full bg-blue-300/20 blur-3xl" />
                <div className="pointer-events-none absolute -bottom-24 left-1/4 h-80 w-80 rounded-full bg-indigo-500/30 blur-3xl" />

                {/* Ambient Grid overlay */}
                <div
                    className="pointer-events-none absolute inset-0 opacity-[0.06]"
                    style={{
                        backgroundImage: `radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)`,
                        backgroundSize: "28px 28px",
                    }}
                />

                {/* Top Header: Brand Logo & Badge */}
                <div className="relative z-10 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/15 p-2 backdrop-blur-md border border-white/30 shadow-inner">
                            <img
                                src="/images/icons/Logo.png"
                                alt="Lumina Logo"
                                className="h-full w-full object-contain drop-shadow"
                            />
                        </div>
                        <span className="text-xl font-bold tracking-tight text-white drop-shadow-sm xl:text-2xl">
                            Lumina
                        </span>
                    </div>

                    <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/15 px-3 py-1 text-xs font-medium tracking-wide text-white/95 backdrop-blur-md shadow-sm">
                        <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span>IF-4MD-08 • PBL 2026</span>
                    </div>
                </div>

                {/* Center Content: SVG Illustration & Tagline */}
                <div className="relative z-10 my-auto flex flex-col items-center py-2 text-center">
                    {/* SVG Illustration: Document + AI Robot + Knowledge Nodes */}
                    <div className="relative mb-4 w-full max-w-[240px] xl:mb-6 xl:max-w-[300px]">
                        <svg
                            viewBox="0 0 400 320"
                            className="h-auto w-full drop-shadow-2xl"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                        >
                            <defs>
                                <linearGradient id="robotGrad" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#ffffff" />
                                    <stop offset="100%" stopColor="#dbeafe" />
                                </linearGradient>
                                <linearGradient id="docGrad" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
                                    <stop offset="100%" stopColor="#e0f2fe" stopOpacity="0.9" />
                                </linearGradient>
                                <linearGradient id="accentBlue" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#38bdf8" />
                                    <stop offset="100%" stopColor="#2563eb" />
                                </linearGradient>
                                <linearGradient id="glowRing" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#67e8f9" stopOpacity="0.6" />
                                    <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.1" />
                                </linearGradient>
                                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                                    <feGaussianBlur stdDeviation="8" result="blur" />
                                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                                </filter>
                            </defs>

                            {/* Background Tech Rings & Connectors */}
                            <ellipse cx="200" cy="270" rx="140" ry="24" fill="url(#glowRing)" />
                            <circle cx="200" cy="150" r="120" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" strokeDasharray="6 6" />
                            <circle cx="200" cy="150" r="85" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />

                            {/* Neural Beam connecting Doc and Robot */}
                            <path
                                d="M125 155 Q 160 110 195 155 T 265 145"
                                stroke="url(#accentBlue)"
                                strokeWidth="3"
                                fill="none"
                                strokeLinecap="round"
                                className="animate-pulse"
                            />

                            {/* Left Document Card (Knowledge Source) */}
                            <g transform="translate(60, 80) rotate(-6)">
                                <rect
                                    width="100"
                                    height="130"
                                    rx="14"
                                    fill="url(#docGrad)"
                                    stroke="rgba(255,255,255,0.6)"
                                    strokeWidth="2"
                                    filter="drop-shadow(0 10px 20px rgba(0,0,0,0.15))"
                                />
                                {/* Header bar in doc */}
                                <rect x="14" y="18" width="40" height="8" rx="4" fill="#3b82f6" />
                                <circle cx="78" cy="22" r="5" fill="#38bdf8" />
                                {/* Lines representing text */}
                                <rect x="14" y="36" width="72" height="5" rx="2.5" fill="#93c5fd" />
                                <rect x="14" y="48" width="62" height="5" rx="2.5" fill="#cbd5e1" />
                                <rect x="14" y="60" width="68" height="5" rx="2.5" fill="#cbd5e1" />
                                <rect x="14" y="72" width="50" height="5" rx="2.5" fill="#cbd5e1" />
                                {/* Mini Graph / Chart */}
                                <rect x="14" y="88" width="72" height="26" rx="6" fill="rgba(59,130,246,0.1)" />
                                <path
                                    d="M20 106 L34 98 L50 102 L64 94 L78 99"
                                    stroke="#2563eb"
                                    strokeWidth="2.5"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    fill="none"
                                />
                            </g>

                            {/* Right Robot / AI Assistant */}
                            <g transform="translate(230, 85)">
                                {/* Floating Shadow */}
                                <ellipse cx="50" cy="145" rx="35" ry="8" fill="rgba(0,0,0,0.2)" />

                                {/* Robot Antenna */}
                                <line x1="50" y1="18" x2="50" y2="4" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
                                <circle cx="50" cy="3" r="5" fill="#38bdf8" filter="url(#glow)" />

                                {/* Robot Head */}
                                <rect
                                    x="10"
                                    y="18"
                                    width="80"
                                    height="62"
                                    rx="20"
                                    fill="url(#robotGrad)"
                                    stroke="rgba(255,255,255,0.8)"
                                    strokeWidth="2"
                                />
                                {/* Visor Screen */}
                                <rect x="20" y="28" width="60" height="34" rx="12" fill="#0f172a" />
                                {/* Glowing Cyan Eyes */}
                                <ellipse cx="36" cy="45" rx="6" ry="8" fill="#38bdf8" />
                                <ellipse cx="64" cy="45" rx="6" ry="8" fill="#38bdf8" />
                                <circle cx="38" cy="42" r="2" fill="#ffffff" />
                                <circle cx="66" cy="42" r="2" fill="#ffffff" />

                                {/* Robot Ears / Audio Sensors */}
                                <rect x="3" y="38" width="7" height="18" rx="3" fill="#93c5fd" />
                                <rect x="90" y="38" width="7" height="18" rx="3" fill="#93c5fd" />

                                {/* Robot Body */}
                                <rect
                                    x="20"
                                    y="84"
                                    width="60"
                                    height="48"
                                    rx="16"
                                    fill="url(#robotGrad)"
                                    stroke="rgba(255,255,255,0.8)"
                                    strokeWidth="2"
                                />
                                {/* Core AI Emblem */}
                                <circle cx="50" cy="105" r="11" fill="#3b82f6" />
                                <path
                                    d="M50 99 L53 103 L57 105 L53 107 L50 111 L47 107 L43 105 L47 103 Z"
                                    fill="#ffffff"
                                />

                                {/* Arms */}
                                <rect x="8" y="88" width="10" height="30" rx="5" fill="#bfdbfe" />
                                <rect x="82" y="88" width="10" height="30" rx="5" fill="#bfdbfe" />
                            </g>

                            {/* Floating Sparkles & Badges */}
                            <g transform="translate(180, 50)">
                                <circle cx="12" cy="12" r="14" fill="rgba(255,255,255,0.2)" />
                                <path d="M12 4 L14 10 L20 12 L14 14 L12 20 L10 14 L4 12 L10 10 Z" fill="#facc15" />
                            </g>
                            <g transform="translate(40, 210)">
                                <circle cx="10" cy="10" r="12" fill="rgba(255,255,255,0.2)" />
                                <path d="M10 4 L11.5 8.5 L16 10 L11.5 11.5 L10 16 L8.5 11.5 L4 10 L8.5 8.5 Z" fill="#38bdf8" />
                            </g>
                        </svg>
                    </div>

                    <h1 className="max-w-md text-xl font-bold tracking-tight text-white lg:text-2xl xl:text-3xl">
                        Analisis Dokumen Cerdas dengan RAG & AI
                    </h1>
                    <p className="mt-2 max-w-md text-xs text-blue-100/85 leading-relaxed xl:text-sm">
                        Tanya jawab dokumen interaktif, perbandingan guideline otomatis, dan pembuatan soal cerdas dengan verifikasi anti-halusinasi.
                    </p>
                </div>

                {/* Bottom Chips / Trust Badges */}
                <div className="relative z-10 flex flex-wrap items-center justify-center gap-2 pt-2">
                    <div className="rounded-xl border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-medium text-white/90 backdrop-blur-md xl:text-xs">
                        Dense + Sparse RRF
                    </div>
                    <div className="rounded-xl border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-medium text-white/90 backdrop-blur-md xl:text-xs">
                        Gemini Vision & OCR
                    </div>
                    <div className="rounded-xl border border-white/20 bg-white/10 px-3 py-1 text-[11px] font-medium text-white/90 backdrop-blur-md xl:text-xs">
                        Groundedness Check
                    </div>
                </div>
            </div>

            {/* ── Right Panel (50% Desktop, Full Width Mobile) ────────────────── */}
            <div
                className="relative flex h-full w-full items-center justify-center p-4 sm:p-6 lg:w-1/2 lg:p-8 overflow-hidden bg-cover bg-center"
                style={{ backgroundImage: "url('/images/Background.png')" }}
            >
                {/* Glass Card Form (AC: backdrop-filter blur(16px), rounded 24px) */}
                <div className="relative w-full max-w-md overflow-hidden rounded-[24px] border border-white/60 bg-white/65 p-6 sm:p-8 shadow-[0_12px_40px_rgba(26,111,168,0.15)] backdrop-blur-[16px] transition-all">
                    {/* Header inside Card */}
                    <div className="mb-5 text-center sm:mb-6">
                        {/* Mobile Brand Header */}
                        <div className="mb-3 flex flex-col items-center lg:hidden">
                            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600/10 p-2 border border-blue-600/20 shadow-sm">
                                <img
                                    src="/images/icons/Logo.png"
                                    alt="Lumina Logo"
                                    className="h-full w-full object-contain"
                                />
                            </div>
                            <span className="mt-1.5 text-lg font-bold text-[#1a3a52]">Lumina</span>
                            <span className="text-[10px] font-medium tracking-wide text-blue-600">
                                IF-4MD-08 • PBL 2026
                            </span>
                        </div>

                        <h2 className="text-xl font-bold tracking-tight text-[#1a3a52] sm:text-2xl">
                            Selamat Datang
                        </h2>
                        <p className="mt-1 text-xs text-[#4a6b82] sm:text-sm">
                            Silakan masuk ke akun Anda untuk melanjutkan
                        </p>
                    </div>

                    {/* Error Banner */}
                    {error && (
                        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50/90 p-3 text-xs text-red-700 shadow-sm backdrop-blur-sm animate-in fade-in duration-200 sm:text-sm">
                            <svg
                                className="mt-0.5 h-4 w-4 shrink-0 text-red-600"
                                fill="currentColor"
                                viewBox="0 0 20 20"
                            >
                                <path
                                    fillRule="evenodd"
                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                    clipRule="evenodd"
                                />
                            </svg>
                            <span className="leading-tight">{error}</span>
                        </div>
                    )}

                    {/* Form Fields */}
                    <form onSubmit={handleSubmit} className="space-y-3.5 sm:space-y-4" noValidate>
                        {/* Email Field */}
                        <div>
                            <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#355872] mb-1 sm:text-xs">
                                Email atau Nama Pengguna
                            </label>
                            <div className="relative">
                                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-[#6a8b9f]">
                                    <svg
                                        className="h-4 w-4"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.206"
                                        />
                                    </svg>
                                </div>
                                <input
                                    type="text"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="nama@email.com atau username"
                                    autoComplete="email"
                                    className="w-full rounded-xl border border-[#b8d5e8]/70 bg-white/70 py-2.5 pl-10 pr-3.5 text-sm text-[#1a3a52] placeholder:text-[#8ba7bc] transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/15"
                                />
                            </div>
                        </div>

                        {/* Password Field with "Tampilkan Sandi" Toggle */}
                        <div>
                            <label className="block text-[11px] font-semibold uppercase tracking-wider text-[#355872] mb-1 sm:text-xs">
                                Kata Sandi
                            </label>
                            <div className="relative">
                                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-[#6a8b9f]">
                                    <svg
                                        className="h-4 w-4"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                                        />
                                    </svg>
                                </div>
                                <input
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Masukkan kata sandi"
                                    autoComplete="current-password"
                                    className="w-full rounded-xl border border-[#b8d5e8]/70 bg-white/70 py-2.5 pl-10 pr-11 text-sm text-[#1a3a52] placeholder:text-[#8ba7bc] transition-all focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/15"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword((prev) => !prev)}
                                    title={showPassword ? "Sembunyikan sandi" : "Tampilkan sandi"}
                                    aria-label={showPassword ? "Sembunyikan sandi" : "Tampilkan sandi"}
                                    className="absolute inset-y-0 right-0 flex items-center pr-3.5 text-[#6a8b9f] hover:text-[#1a3a52] focus:outline-none transition-colors"
                                >
                                    {showPassword ? (
                                        <svg
                                            className="h-4 w-4"
                                            fill="none"
                                            viewBox="0 0 24 24"
                                            stroke="currentColor"
                                        >
                                            <path
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                strokeWidth={2}
                                                d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                                            />
                                        </svg>
                                    ) : (
                                        <svg
                                            className="h-4 w-4"
                                            fill="none"
                                            viewBox="0 0 24 24"
                                            stroke="currentColor"
                                        >
                                            <path
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                strokeWidth={2}
                                                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                                            />
                                            <path
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                strokeWidth={2}
                                                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                                            />
                                        </svg>
                                    )}
                                </button>
                            </div>
                        </div>

                        {/* "Ingat Saya" Checkbox & "Lupa kata sandi?" Link */}
                        <div className="flex items-center justify-between pt-0.5">
                            <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-[#355872]">
                                <input
                                    type="checkbox"
                                    checked={rememberMe}
                                    onChange={(e) => setRememberMe(e.target.checked)}
                                    className="h-4 w-4 rounded border-[#9fc1d8] text-blue-600 focus:ring-blue-500 focus:ring-offset-0"
                                />
                                <span>Ingat saya</span>
                            </label>

                            <Link
                                href="/change-password"
                                className="text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                            >
                                Lupa kata sandi?
                            </Link>
                        </div>

                        {/* Button "Masuk" (AC: gradient blue, full width) */}
                        <div className="pt-1.5">
                            <button
                                type="submit"
                                disabled={loading}
                                className="relative flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#175ea1] via-[#2563eb] to-[#3b82f6] px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-blue-600/25 transition-all duration-200 hover:from-[#134e86] hover:to-[#1d4ed8] hover:shadow-lg hover:shadow-blue-600/35 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
                            >
                                {loading ? (
                                    <>
                                        <svg
                                            className="h-4 w-4 animate-spin text-white"
                                            xmlns="http://www.w3.org/2000/svg"
                                            fill="none"
                                            viewBox="0 0 24 24"
                                        >
                                            <circle
                                                className="opacity-25"
                                                cx="12"
                                                cy="12"
                                                r="10"
                                                stroke="currentColor"
                                                strokeWidth="4"
                                            />
                                            <path
                                                className="opacity-75"
                                                fill="currentColor"
                                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                            />
                                        </svg>
                                        <span>Memproses…</span>
                                    </>
                                ) : (
                                    <span>Masuk</span>
                                )}
                            </button>
                        </div>

                        {/* Link "Daftar di sini" ke halaman register */}
                        <div className="pt-2 text-center text-xs text-[#52748d]">
                            <span>Belum punya akun? </span>
                            <Link
                                href="/register"
                                className="font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                            >
                                Daftar di sini
                            </Link>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
}
