"use client";

import { Fragment, type ReactNode } from "react";

/**
 * Renderer Markdown ringan (tanpa dependensi eksternal).
 * Mendukung: heading, paragraf, bold/italic, inline code, code block,
 * list berurutan/tidak, blockquote, horizontal rule, dan tabel dasar.
 */

const INLINE_PATTERN =
    /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[([^\]]+)\]\(([^)\s]+)\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
    const nodes: ReactNode[] = [];
    const pattern = new RegExp(INLINE_PATTERN.source, INLINE_PATTERN.flags);
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    let idx = 0;

    while ((match = pattern.exec(text)) !== null) {
        if (match.index > lastIndex) {
            nodes.push(
                <Fragment key={`${keyPrefix}-t${idx++}`}>
                    {text.slice(lastIndex, match.index)}
                </Fragment>,
            );
        }
        const [full, code, bold, italic, , linkText, linkHref] = match;
        const key = `${keyPrefix}-m${idx++}`;
        if (code) {
            nodes.push(
                <code
                    key={key}
                    className="rounded bg-[#1a3a52]/10 px-1.5 py-0.5 font-mono text-[0.85em] text-[#1a6fa8]"
                >
                    {code.slice(1, -1)}
                </code>,
            );
        } else if (bold) {
            nodes.push(
                <strong key={key} className="font-semibold">
                    {renderInline(bold.slice(2, -2), key)}
                </strong>,
            );
        } else if (italic) {
            nodes.push(<em key={key}>{renderInline(italic.slice(1, -1), key)}</em>);
        } else if (linkHref) {
            nodes.push(
                <a
                    key={key}
                    href={linkHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-[#1a6fa8] underline underline-offset-2"
                >
                    {linkText}
                </a>,
            );
        } else {
            nodes.push(<Fragment key={key}>{full}</Fragment>);
        }
        lastIndex = match.index + full.length;
    }

    if (lastIndex < text.length) {
        nodes.push(<Fragment key={`${keyPrefix}-t${idx++}`}>{text.slice(lastIndex)}</Fragment>);
    }
    return nodes;
}

function isTableSeparatorRow(cells: string[]): boolean {
    return cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function renderBlocks(lines: string[], keyPrefix: string): ReactNode[] {
    const nodes: ReactNode[] = [];
    let i = 0;

    while (i < lines.length) {
        const raw = lines[i];
        const trimmed = raw.trim();
        const key = `${keyPrefix}-b${i}`;

        if (!trimmed) {
            i++;
            continue;
        }

        // ── Code block ──────────────────────────────────────────────
        if (trimmed.startsWith("```")) {
            const buf: string[] = [];
            i++;
            while (i < lines.length && !lines[i].trim().startsWith("```")) {
                buf.push(lines[i]);
                i++;
            }
            i++; // skip closing fence
            nodes.push(
                <pre
                    key={key}
                    className="my-3 overflow-x-auto rounded-xl border border-white/40 bg-[#0f2436]/90 p-4 text-sm text-white/90"
                >
                    <code>{buf.join("\n")}</code>
                </pre>,
            );
            continue;
        }

        // ── Heading ─────────────────────────────────────────────────
        const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
        if (heading) {
            const level = heading[1].length as 1 | 2 | 3 | 4 | 5 | 6;
            const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
            const sizes: Record<number, string> = {
                1: "text-xl font-semibold",
                2: "text-lg font-semibold",
                3: "text-base font-semibold",
                4: "text-base font-medium",
                5: "text-sm font-medium",
                6: "text-sm font-medium",
            };
            nodes.push(
                <Tag key={key} className={`mt-3 mb-1 ${sizes[level]}`}>
                    {renderInline(heading[2], key)}
                </Tag>,
            );
            i++;
            continue;
        }

        // ── Horizontal rule ─────────────────────────────────────────
        if (/^([-*_])[ \t]*\1[ \t]*\1[ \t]*$/.test(trimmed)) {
            nodes.push(<hr key={key} className="my-3 border-white/30" />);
            i++;
            continue;
        }

        // ── Blockquote ──────────────────────────────────────────────
        if (trimmed.startsWith(">")) {
            const buf: string[] = [];
            while (i < lines.length && lines[i].trim().startsWith(">")) {
                buf.push(lines[i].trim().replace(/^>\s?/, ""));
                i++;
            }
            nodes.push(
                <blockquote
                    key={key}
                    className="my-2 border-l-4 border-[#1a6fa8]/50 pl-3 text-sm italic text-[#1a3a52]/80"
                >
                    {renderBlocks(buf, key)}
                </blockquote>,
            );
            continue;
        }

        // ── Unordered list ──────────────────────────────────────────
        if (/^\s*([-*+])\s+/.test(trimmed)) {
            const items: ReactNode[] = [];
            while (i < lines.length) {
                const m = lines[i].trim().match(/^\s*([-*+])\s+(.*)$/);
                if (!m) break;
                items.push(
                    <li key={`${key}-li${i}`} className="ml-5 list-disc">
                        {renderInline(m[2], `${key}-li${i}`)}
                    </li>,
                );
                i++;
            }
            nodes.push(<ul key={key} className="my-2 space-y-1.5">{items}</ul>);
            continue;
        }

        // ── Ordered list ────────────────────────────────────────────
        if (/^\s*\d+[.)]\s+/.test(trimmed)) {
            const items: ReactNode[] = [];
            while (i < lines.length) {
                const m = lines[i].trim().match(/^\s*\d+[.)]\s+(.*)$/);
                if (!m) break;
                items.push(
                    <li key={`${key}-li${i}`} className="ml-5 list-decimal">
                        {renderInline(m[1], `${key}-li${i}`)}
                    </li>,
                );
                i++;
            }
            nodes.push(<ol key={key} className="my-2 space-y-1.5">{items}</ol>);
            continue;
        }

        // ── Table ───────────────────────────────────────────────────
        if (trimmed.startsWith("|")) {
            const rows: string[][] = [];
            const tableStartIndex = i;
            while (i < lines.length && lines[i].trim().startsWith("|")) {
                const cells = lines[i]
                    .trim()
                    .split("|")
                    .slice(1, -1)
                    .map((c) => c.trim());
                rows.push(cells);
                i++;
            }
            if (rows.length >= 2 && isTableSeparatorRow(rows[1] ?? [])) {
                const header = rows[0];
                const body = rows.slice(2);
                nodes.push(
                    <div key={key} className="my-3 overflow-x-auto rounded-xl border border-white/40 bg-white/30">
                        <table className="w-full border-collapse text-sm">
                            <thead>
                                <tr>
                                    {header.map((cell, ci) => (
                                        <th
                                            key={`${key}-th${ci}`}
                                            className="border-b border-white/40 px-3 py-1.5 text-left font-semibold text-[#1a3a52]"
                                        >
                                            {renderInline(cell, `${key}-th${ci}`)}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {body.map((row, ri) => (
                                    <tr key={`${key}-tr${ri}`}>
                                        {row.map((cell, ci) => (
                                            <td
                                                key={`${key}-td${ri}-${ci}`}
                                                className="border-b border-white/30 px-3 py-1.5 text-[#1a3a52]/90"
                                            >
                                                {renderInline(cell, `${key}-td${ri}-${ci}`)}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>,
                );
                continue;
            } else {
                i = tableStartIndex + 1;
                const para: string[] = [trimmed];
                while (i < lines.length) {
                    const t = lines[i].trim();
                    if (!t) break;
                    if (/^(#{1,6})\s/.test(t)) break;
                    if (t.startsWith("```")) break;
                    if (t.startsWith(">")) break;
                    if (t.startsWith("|")) break;
                    if (/^\s*([-*+]|\d+[.)])\s+/.test(t)) break;
                    if (/^([-*_])[ \t]*\1[ \t]*\1[ \t]*$/.test(t)) break;
                    para.push(t);
                    i++;
                }
                nodes.push(
                    <p key={key} className="my-2 leading-relaxed">
                        {renderInline(para.join(" "), key)}
                    </p>,
                );
                continue;
            }
        }

        // ── Paragraph (kumpulkan baris sampai block berikutnya) ─────
        const para: string[] = [];
        while (i < lines.length) {
            const t = lines[i].trim();
            if (!t) break;
            if (/^(#{1,6})\s/.test(t)) break;
            if (t.startsWith("```")) break;
            if (t.startsWith(">")) break;
            if (t.startsWith("|")) break;
            if (/^\s*([-*+]|\d+[.)])\s+/.test(t)) break;
            if (/^([-*_])[ \t]*\1[ \t]*\1[ \t]*$/.test(t)) break;
            para.push(t);
            i++;
        }
        if (para.length) {
            nodes.push(
                <p key={key} className="my-2 leading-relaxed">
                    {renderInline(para.join(" "), key)}
                </p>,
            );
        }
    }

    return nodes;
}

export default function Markdown({ content }: MarkdownProps) {
    if (!content) return null;
    const lines = content.split(/\r?\n/);
    return <div className="text-sm">{renderBlocks(lines, "md")}</div>;
}

interface MarkdownProps {
    content: string;
}
