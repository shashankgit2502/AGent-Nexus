"use client";

/**
 * Final Output canvas (§9.7) — collapsed/empty during debate, then renders the
 * synthesized result when the synthesizer node emits. Lifecycle-driven off the
 * store: "Synthesizing…" once the run is past HITL but before `synthesis`, then
 * the synthesis content blocks, then the finished artifact (markdown) with copy.
 * A `reject` decision shows the rejected terminal state honestly.
 */
import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Clipboard, FileText, Sparkles, Ban, Loader2 } from "lucide-react";
import { useSessionStore } from "@/store/session-store";
import { ContentBlocks } from "@/components/content-blocks/content-block";
import { Markdown } from "@/components/ui/markdown";
import { ArtifactsSection } from "@/components/artifacts/artifacts-section";

export function OutputCanvas() {
  const status = useSessionStore((s) => s.run.status);
  const synthesis = useSessionStore((s) => s.run.synthesis);
  const artifact = useSessionStore((s) => s.run.artifact);
  const hitl = useSessionStore((s) => s.run.hitl);

  const rejected = synthesis?.rejected || artifact?.kind === "rejected";
  const synthesizing =
    !synthesis && !artifact && (status === "running" || status === "awaiting_human") &&
    hitl?.status === "resolved";

  return (
    <div className="w-full h-full bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden flex flex-col">
      <div className="px-4 py-3 border-b border-[#27272a]/80 bg-[#18181b] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-emerald-400" />
          <div>
            <h4 className="text-[12px] font-bold text-zinc-200 tracking-wide uppercase">
              Final Output
            </h4>
            <p className="text-[9.5px] text-zinc-500 font-mono">Synthesizer canvas</p>
          </div>
        </div>
        {artifact ? <CopyButton text={artifact.content ?? ""} /> : null}
      </div>

      <div className="flex-1 overflow-y-auto p-4 min-h-[200px]">
        {rejected ? (
          <Centered icon={<Ban className="w-9 h-9 opacity-30 text-rose-400" />} title="Output rejected">
            The human gate rejected the candidate; no artifact was synthesized.
          </Centered>
        ) : artifact?.content ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="text-[12px] leading-relaxed text-zinc-200 font-sans"
          >
            <Markdown content={artifact.content} />
          </motion.div>
        ) : synthesis?.contentBlocks?.length ? (
          <ContentBlocks blocks={synthesis.contentBlocks} />
        ) : synthesizing ? (
          <Centered icon={<Loader2 className="w-8 h-8 opacity-40 animate-spin text-emerald-400" />} title="Synthesizing…">
            Folding the highest-ranked contributions into a single output.
          </Centered>
        ) : (
          <Centered icon={<Sparkles className="w-8 h-8 opacity-20" />} title="Awaiting synthesis">
            The output canvas expands when the run reaches the synthesizer.
          </Centered>
        )}

        {/* Downloadable file artifacts produced post-consensus (§9.7 / ARTIFACTS §12).
            Renders nothing until the producer emits a file. */}
        <ArtifactsSection />
      </div>
    </div>
  );
}

function Centered({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center text-zinc-500 p-6">
      <div className="mb-3">{icon}</div>
      <h5 className="text-zinc-300 text-xs font-semibold mb-1">{title}</h5>
      <p className="text-[10.5px] text-zinc-600 max-w-[320px]">{children}</p>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard unavailable — non-fatal.
    }
  };
  return (
    <button
      type="button"
      onClick={onCopy}
      disabled={!text}
      className="flex items-center gap-1.5 px-2.5 py-1 text-[10.5px] font-medium text-zinc-300 bg-[#27272a]/60 hover:bg-[#27272a] border border-[#27272a] rounded-lg transition-all disabled:opacity-40 disabled:pointer-events-none"
    >
      {copied ? (
        <>
          <Check className="w-3.5 h-3.5 text-green-400" />
          <span className="text-[10px] text-green-400">Copied</span>
        </>
      ) : (
        <>
          <Clipboard className="w-3.5 h-3.5" />
          <span className="text-[10px]">Copy</span>
        </>
      )}
    </button>
  );
}
