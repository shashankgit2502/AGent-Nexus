"use client";

/**
 * ContentBlock renderer — the A2UI seam (§24.6). The discriminated union is
 * extensible; today's variants are text / code / tool_result. Keeping this in
 * one component means every panel (debate, synthesis, blackboard) renders blocks
 * identically, and a future A2UI widget variant slots in here only.
 */
import { useState } from "react";
import { Check, Clipboard } from "lucide-react";
import { Markdown } from "@/components/ui/markdown";
import type { ContentBlock } from "@/types/agui";

interface ContentBlockViewProps {
  block: ContentBlock;
}

export function ContentBlockView({ block }: ContentBlockViewProps) {
  switch (block.type) {
    case "text":
      return <Markdown content={block.text} className="text-[11.5px] text-zinc-300" />;
    case "code":
      return <CodeBlock language={block.language} code={block.code} />;
    case "tool_result":
      return (
        <div className="rounded border border-white/5 bg-black/40 p-2.5">
          <p className="text-[8.5px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-1">
            Tool · {block.tool}
          </p>
          <p className="text-[11px] font-mono text-zinc-300 whitespace-pre-wrap break-words">
            {block.value}
          </p>
        </div>
      );
    default:
      // Exhaustive today; an unknown block type is contract drift (§24.6).
      return null;
  }
}

/** Render a list of blocks with consistent spacing. */
export function ContentBlocks({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="space-y-2">
      {blocks.map((block, i) => (
        <ContentBlockView key={i} block={block} />
      ))}
    </div>
  );
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard blocked (insecure context / denied) — non-fatal, no-op.
    }
  };
  return (
    <div className="rounded-lg border border-white/5 bg-[#09090b] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5 bg-[#111113]">
        <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-emerald-400">
          {language || "code"}
        </span>
        <button
          type="button"
          onClick={onCopy}
          className="flex items-center gap-1 text-[9px] font-mono text-zinc-400 hover:text-white transition-colors"
        >
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Clipboard className="w-3 h-3" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-[11px] leading-6 font-mono text-zinc-200">
        <code>{code}</code>
      </pre>
    </div>
  );
}
