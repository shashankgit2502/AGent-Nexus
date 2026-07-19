"use client";

/**
 * ArtifactPreview — per-kind renderer for the panel (ARTIFACTS.md §12).
 *
 * Slice 2 covers the text kinds (markdown / code / json / csv); binary kinds
 * (docx/xlsx/pptx/pdf/image/archive) and storage-spilled text have `preview: null`
 * and show a "download to view" notice (their rich preview lands in Slice 4). The
 * preview string is a **bounded** server-side excerpt (§11.1), so a notice is shown
 * when content is truncated. Untrusted content is rendered as **text only** — never
 * executed (markdown via the shared sanitised renderer; no raw HTML, §15).
 */
import { Download } from "lucide-react";
import { Markdown } from "@/components/ui/markdown";
import type { ArtifactFileKind } from "@/types/agui";

interface ArtifactPreviewProps {
  kind: ArtifactFileKind;
  /** Full content for text kinds; null for binary or when no preview is available. */
  content: string | null;
}

export function ArtifactPreview({ kind, content }: ArtifactPreviewProps) {
  if (content === null || content === "") {
    return <NoPreview />;
  }

  switch (kind) {
    case "markdown":
      return <Markdown content={content} className="text-[12px] text-zinc-200" />;
    case "csv":
      return <CsvTable text={content} />;
    case "json":
      return <CodePane text={prettyJson(content)} />;
    case "code":
      return <CodePane text={content} />;
    default:
      // Binary kinds carry no inline preview (content was null above); reaching here
      // means a text-ish kind we don't specially render → show it as plain code.
      return <CodePane text={content} />;
  }
}

function NoPreview() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center text-zinc-500 py-10">
      <Download className="w-8 h-8 opacity-30 mb-3" />
      <p className="text-[11px] text-zinc-400">No inline preview for this file type.</p>
      <p className="text-[10px] text-zinc-600 mt-1">Use Download to open it.</p>
    </div>
  );
}

function CodePane({ text }: { text: string }) {
  return (
    <pre className="rounded-lg border border-white/5 bg-[#09090b] p-3 overflow-x-auto text-[11.5px] leading-relaxed font-mono text-zinc-200 whitespace-pre">
      <code>{text}</code>
    </pre>
  );
}

/** Best-effort pretty-print; raw text if it is not (any longer) valid JSON. */
function prettyJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

/**
 * Render CSV preview as a table. Deliberately a *naive* split (no quoted-comma
 * handling) — this is a preview, not a parser; the downloaded file is authoritative.
 * Rows are capped so a large preview never blows up the panel.
 */
const MAX_PREVIEW_ROWS = 50;

function CsvTable({ text }: { text: string }) {
  const rows = text
    .trim()
    .split(/\r?\n/)
    .slice(0, MAX_PREVIEW_ROWS)
    .map((line) => line.split(","));
  const header = rows[0];
  if (!header) return <CodePane text={text} />;
  const body = rows.slice(1);

  return (
    <div className="overflow-x-auto rounded-lg border border-white/10">
      <table className="w-full text-left text-[11px] border-collapse">
        <thead className="bg-white/[0.04]">
          <tr>
            {header.map((cell, i) => (
              <th
                key={i}
                className="px-2.5 py-1.5 font-semibold text-zinc-200 border-b border-white/10 whitespace-nowrap"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td
                  key={c}
                  className="px-2.5 py-1 text-zinc-300 border-b border-white/5 align-top whitespace-nowrap"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
