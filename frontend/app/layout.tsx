import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
    variable: "--font-space-grotesk",
    subsets: ["latin"],
});

export const metadata: Metadata = {
    title: {
        default: "Lumina",
        template: "%s — Lumina",
    },
    description:
        "Sistem RAG untuk analisis dokumen cerdas — tanya jawab, perbandingan, dan pembuatan soal otomatis.",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="id" className="h-full">
            <body
                className={`${spaceGrotesk.variable} h-full font-sans antialiased`}
            >
                {children}
            </body>
        </html>
    );
}
