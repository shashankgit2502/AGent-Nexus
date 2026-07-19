"use client";

/**
 * Markdown — shared GitHub-flavoured-markdown renderer for model output.
 *
 * Model turns (chat assistant messages, synthesizer artifacts, synthesis text
 * blocks) arrive as markdown strings. Before this they were dumped raw inside a
 * `whitespace-pre-wrap` div, so users saw literal `###`, `**bold**`, and `- `
 * list markers (Bug 1). This component renders that markdown to styled elements
 * with `react-markdown` + `remark-gfm` (tables, strikethrough, task lists, auto
 * links), themed for the obsidian/emerald UI.
 *
 * It is deliberately self-contained: every element has explicit Tailwind classes
 * (no `@tailwindcss/typography` dependency) so it inherits cleanly into chat
 * bubbles and the output canvas alike. Pass a wrapper `className` to set the base
 * text size/colour for the surrounding surface.
 */
import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Clipboard } from "lucide-react";
import { cn } from "@/lib/utils";

interface MarkdownProps {
  content: string;
  /** Base styling for the surface (text size/colour). */
  className?: string;
}

/** Fenced code block with a language label and copy button. */
function CodeFence({ language, code }: { language: string; code: string }) {
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
    <div className="my-2.5 rounded-lg border border-white/5 bg-[#09090b] overflow-hidden not-prose">
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
      <pre className="px-3 py-2.5 overflow-x-auto text-[11.5px] leading-relaxed font-mono text-zinc-200">
        <code>{code}</code>
      </pre>
    </div>
  );
}

const COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="text-[15px] font-bold text-white mt-3 mb-1.5 first:mt-0 tracking-tight">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-[14px] font-bold text-white mt-3 mb-1.5 first:mt-0 tracking-tight">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-[13px] font-bold text-zinc-100 mt-2.5 mb-1 first:mt-0 tracking-tight">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-[12px] font-semibold text-zinc-100 mt-2 mb-1 first:mt-0 uppercase tracking-wider">
      {children}
    </h4>
  ),
  p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-1.5 ml-1 space-y-1 list-disc list-outside pl-4 marker:text-emerald-400/70">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-1.5 ml-1 space-y-1 list-decimal list-outside pl-4 marker:text-emerald-400/70 marker:font-mono">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-relaxed pl-1">{children}</li>,
  strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-zinc-100">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-emerald-400 underline underline-offset-2 decoration-emerald-400/40 hover:decoration-emerald-400 transition-colors"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-emerald-500/40 pl-3 text-zinc-400 italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-white/10" />,
  code: ({ className, children, ...props }) => {
    const match = /language-(\w+)/.exec(className ?? "");
    const text = String(children ?? "").replace(/\n$/, "");
    // react-markdown gives block code a `language-*` class or multi-line content;
    // inline code is short and class-less.
    if (match || text.includes("\n")) {
      return <CodeFence language={match?.[1] ?? ""} code={text} />;
    }
    return (
      <code
        className="px-1.5 py-0.5 rounded bg-white/[0.08] border border-white/10 font-mono text-[11px] text-emerald-300"
        {...props}
      >
        {children}
      </code>
    );
  },
  pre: ({ children }: { children?: ReactNode }) => <>{children}</>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-white/10 not-prose">
      <table className="w-full text-left text-[11.5px] border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/[0.04]">{children}</thead>,
  th: ({ children }) => (
    <th className="px-3 py-1.5 font-semibold text-zinc-200 border-b border-white/10">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-1.5 text-zinc-300 border-b border-white/5 align-top">{children}</td>
  ),
};

export function Markdown({ content, className }: MarkdownProps) {
  return (
    <div className={cn("break-words", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
