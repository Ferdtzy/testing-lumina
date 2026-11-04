"use client";

interface DocumentStat {
    label: string;
    value: number;
    icon: React.ReactNode;
    color: string;
    textColor: string;
}

interface DocumentStatsProps {
    stats: { total: number; indexed: number; processing: number; failed: number };
}

export default function DocumentStats({ stats }: DocumentStatsProps) {
    const statCards = [
        {
            label: "Total Dokumen",
            value: stats.total,
            icon: (
                <svg className="h-5 w-5 text-blue-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                </svg>
            ),
            color: "bg-blue-100",
            textColor: "text-[#1a3a52]",
        },
        {
            label: "Berhasil Di-index",
            value: stats.indexed,
            icon: (
                <svg className="h-5 w-5 text-green-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
            ),
            color: "bg-green-100",
            textColor: "text-green-600",
        },
        {
            label: "Processing",
            value: stats.processing,
            icon: (
                <svg className="h-5 w-5 text-orange-600 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
                </svg>
            ),
            color: "bg-orange-100",
            textColor: "text-orange-600",
        },
        {
            label: "Gagal",
            value: stats.failed,
            icon: (
                <svg className="h-5 w-5 text-red-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
            ),
            color: "bg-red-100",
            textColor: "text-red-600",
        },
    ] as DocumentStat[];

    return (
        <div className="shrink-0 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {statCards.map((card, index) => (
                <div
                    key={index}
                    className="rounded-2xl p-4 [background:rgba(255,255,255,0.1)] [border:1px_solid_rgba(255,255,255,0.18)] [box-shadow:0_2px_4px_rgba(0,0,0,0.15)] [backdrop-filter:blur(20px)] [-webkit-backdrop-filter:blur(20px)]"
                >
                    <div className="flex items-center gap-3">
                        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${card.color}`}>
                            {card.icon}
                        </div>
                        <div>
                            <p className="text-xs font-medium uppercase tracking-wide text-[#1a3a52]/50">
                                {card.label}
                            </p>
                            <p className={`text-2xl font-semibold ${card.textColor}`}>
                                {card.value}
                            </p>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}
