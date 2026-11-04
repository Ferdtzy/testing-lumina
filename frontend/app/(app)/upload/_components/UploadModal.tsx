"use client";

import { useState, useRef } from "react";

interface UploadModalProps {
    isOpen: boolean;
    onClose: () => void;
    onUpload: (file: File) => Promise<void>;
    isUploading: boolean;
    uploadError: string | null;
}

export default function UploadModal({ isOpen, onClose, onUpload, isUploading, uploadError }: UploadModalProps) {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const ALLOWED_EXTENSIONS = [
        ".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp",
    ];

    function validateFile(file: File): string | null {
        const ext = "." + file.name.split(".").pop()?.toLowerCase();

        if (!ALLOWED_EXTENSIONS.includes(ext)) {
            return `Tipe file tidak didukung: ${ext}`;
        }

        if (file.size > 100 * 1024 * 1024) {
            return "Ukuran file melebihi batas 100 MB.";
        }

        return null;
    }

    function handleFile(file: File) {
        const error = validateFile(file);

        if (error) {
            return;
        }

        setSelectedFile(file);
    }

    const onDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(true);
    };

    const onDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
    };

    const onDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);

        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
    };

    function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];

        if (file) handleFile(file);

        event.target.value = "";
    }

    async function submitUpload() {
        if (!selectedFile) return;

        await onUpload(selectedFile);

        setSelectedFile(null);
    }

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div
                className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-[#1a3a52]">
                        Upload Dokumen
                    </h2>

                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-lg p-1 text-[#1a3a52]/50 transition-colors hover:bg-gray-100 hover:text-[#1a3a52]"
                    >
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {uploadError && (
                    <div className="mb-4 rounded-xl border border-red-200 bg-red-50/90 p-3 text-xs text-red-700 shadow-sm">
                        {uploadError}
                    </div>
                )}

                <div
                    onClick={() => fileInputRef.current?.click()}
                    className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
                        isDragOver
                            ? "border-[#1a6fa8] bg-[#1a6fa8]/5"
                            : selectedFile
                                ? "border-green-400 bg-green-50"
                                : "border-gray-300 hover:border-[#1a6fa8]/50"
                    }`}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.bmp,.tiff,.webp"
                        className="hidden"
                        onChange={handleFileInputChange}
                    />

                    {selectedFile ? (
                        <>
                            <svg className="mb-3 h-10 w-10 text-green-500" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H5.625C5.004 2.25 4.5 2.754 4.5 3.375v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                            </svg>

                            <p className="text-sm font-medium text-[#1a3a52]">
                                {selectedFile.name}
                            </p>

                            <p className="mt-1 text-xs text-[#1a3a52]/60">
                                {Math.round(selectedFile.size / 1024)} KB
                            </p>

                            <div className="mt-6 flex gap-3">
                                <button
                                    onClick={submitUpload}
                                    disabled={isUploading}
                                    className="rounded-xl bg-[#1a6fa8] px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#155a85] disabled:opacity-60"
                                >
                                    {isUploading ? "Mengunggah..." : "Unggah"}
                                </button>
                                <button
                                    onClick={() => setSelectedFile(null)}
                                    className="rounded-xl border border-gray-300 px-5 py-2 text-sm text-[#1a3a52] transition-colors hover:bg-gray-50"
                                >
                                    Batal
                                </button>
                            </div>
                        </>
                    ) : (
                        <>
                            <svg className="mb-3 h-10 w-10 text-[#1a6fa8]" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                            </svg>

                            <p className="text-sm font-medium text-[#1a3a52]">
                                Drag & drop dokumen di sini
                            </p>
                            <p className="mt-1 text-xs text-[#1a3a52]/60">
                                atau klik untuk memilih file
                            </p>
                            <p className="mt-2 text-xs text-[#1a3a52]/40">
                                PDF, DOCX, TXT, JPG, PNG, BMP, TIFF, WEBP (maks 100 MB)
                            </p>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
