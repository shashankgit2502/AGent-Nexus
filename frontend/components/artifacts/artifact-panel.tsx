"use client";

/**
 * ArtifactPanel — the Canvas detail view for one artifact (ARTIFACTS.md §12).
 *
 * Slice 3 (panel parity): per-kind **preview** of the active version, a **version
 * switcher** (v1/v2/…, Canvas history), **iterate** (instruction → new version),
 * **copy**, **open in editor** (new tab), and a prominent **download** — all over the
 * authenticated artifact API (any version, no token-expiry). Live `generating →
 * ready` status drives the badge. Rendered as a fixed overlay so it works unchanged in
 * the Session Workspace and chat (its mount, OutputCanvas, lives in both).
 */
import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Ban,
  Check,
  Clipboard,
  Download,
  ExternalLink,
  History,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { artifactIcon } from "@/components/artifacts/artifact-icon";
import { ArtifactPreview } from "@/components/artifacts/artifact-preview";
import {
  downloadArtifactFile,
  fetchArtifactBlob,
  fetchArtifactText,
  getArtifact,
  iterateArtifact,
  openArtifactInTab,
  type ArtifactDetailDto,
  type ArtifactVersionDto,
} from "@/lib/api/artifacts";
import { formatBytes } from "@/lib/artifacts";
import { useSessionStore } from "@/store/session-store";
import type { ArtifactEntry } from "@/store/session-reducer";
import type { ArtifactFileKind } from "@/types/agui";

const TEXT_KINDS: ReadonlySet<ArtifactFileKind> = new Set(["markdown", "code", "json", "csv"]);
const ITERABLE_KINDS = TEXT_KINDS;

interface ArtifactPanelProps {
  artifact: ArtifactEntry;
  onClose: () => void;
}

function detailToEntry(d: ArtifactDetailDto): ArtifactEntry {
  return {
    artifactId: d.id,
    kind: d.kind,
    filename: d.filename,
    mimeType: d.mime_type,
    version: d.current_version,
    status: d.status,
    preview: d.preview,
    downloadUrl: d.download_url,
    sizeBytes: d.size_bytes,
    producerAgentId: d.producer_agent_id,
  };
}

export function ArtifactPanel({ artifact, onClose }: ArtifactPanelProps) {
  const updateArtifact = useSessionStore((s) => s.updateArtifact);
  const Icon = artifactIcon(artifact.kind);
  const filename = artifact.filename ?? `artifact.${artifact.kind}`;
  const isText = TEXT_KINDS.has(artifact.kind);
  const isImage = artifact.kind === "image";

  const [detail, setDetail] = useState<ArtifactDetailDto | null>(null);
  const [activeVersion, setActiveVersion] = useState<number>(artifact.version);
  const [text, setText] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadingText, setLoadingText] = useState(false);
  const [iterating, setIterating] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [showIterate, setShowIterate] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const id = artifact.artifactId;
  const versions: ArtifactVersionDto[] = detail?.versions ?? [
    { version: artifact.version, size_bytes: artifact.sizeBytes, created_at: "" },
  ];
  const status = detail?.status ?? artifact.status;
  const generating = status === "generating";
  const failed = status === "failed";
  const activeSize =
    versions.find((v) => v.version === activeVersion)?.size_bytes ?? artifact.sizeBytes;

  // Load metadata + version list once (fall back to the store entry on failure).
  useEffect(() => {
    let cancelled = false;
    getArtifact(id)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setActiveVersion(d.current_version);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load artifact");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Load the active version's full text (text kinds only) for the preview + copy.
  useEffect(() => {
    if (!isText || generating || failed) {
      setText(null);
      return;
    }
    let cancelled = false;
    setLoadingText(true);
    fetchArtifactText(id, activeVersion)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch(() => {
        if (!cancelled) setText(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingText(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, activeVersion, isText, generating, failed]);

  // Load the active version as an object URL for inline image preview (image kinds).
  useEffect(() => {
    if (!isImage || generating || failed) {
      setImageUrl(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    fetchArtifactBlob(id, activeVersion)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setImageUrl(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id, activeVersion, isImage, generating, failed]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onDownload = useCallback(() => {
    void downloadArtifactFile(id, filename, activeVersion).catch((e: unknown) =>
      setError(e instanceof Error ? e.message : "download failed"),
    );
  }, [id, filename, activeVersion]);

  const onOpen = useCallback(() => {
    void openArtifactInTab(id, activeVersion).catch((e: unknown) =>
      setError(e instanceof Error ? e.message : "open failed"),
    );
  }, [id, activeVersion]);

  const onCopy = useCallback(async () => {
    if (text === null) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard blocked — non-fatal.
    }
  }, [text]);

  const onIterate = useCallback(async () => {
    const trimmed = instruction.trim();
    if (!trimmed || iterating) return;
    setIterating(true);
    setError(null);
    try {
      const updated = await iterateArtifact(id, trimmed);
      setDetail(updated);
      setActiveVersion(updated.current_version);
      setInstruction("");
      setShowIterate(false);
      updateArtifact(detailToEntry(updated)); // keep the Final Output card in sync
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "iterate failed");
    } finally {
      setIterating(false);
    }
  }, [id, instruction, iterating, updateArtifact]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        role="dialog"
        aria-modal="true"
        aria-label={`Artifact ${filename}`}
        className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-[#111113] border border-[#27272a] rounded-xl overflow-hidden shadow-2xl"
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-[#27272a]/80 bg-[#18181b] flex items-center gap-3">
          <span className="grid place-items-center w-9 h-9 rounded-md bg-emerald-500/10 border border-emerald-500/20">
            <Icon className="w-4 h-4 text-emerald-400" />
          </span>
          <div className="min-w-0 flex-1">
            <h4 className="text-[13px] font-semibold text-zinc-100 truncate">{filename}</h4>
            <p className="text-[9.5px] font-mono text-zinc-500 uppercase tracking-wide">
              {artifact.kind} · {formatBytes(activeSize)} · v{activeVersion}
            </p>
          </div>
          <StatusBadge generating={generating} failed={failed} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid place-items-center w-7 h-7 rounded-lg text-zinc-400 hover:text-white hover:bg-[#27272a] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="px-4 py-2 border-b border-[#27272a]/60 bg-[#141417] flex items-center gap-2 flex-wrap">
          <ToolbarButton onClick={onDownload} disabled={generating} icon={<Download className="w-3.5 h-3.5" />}>
            Download
          </ToolbarButton>
          {isText ? (
            <ToolbarButton onClick={() => void onCopy()} disabled={text === null} icon={copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Clipboard className="w-3.5 h-3.5" />}>
              {copied ? "Copied" : "Copy"}
            </ToolbarButton>
          ) : null}
          {isText || isImage ? (
            <ToolbarButton onClick={onOpen} disabled={generating} icon={<ExternalLink className="w-3.5 h-3.5" />}>
              Open
            </ToolbarButton>
          ) : null}
          {ITERABLE_KINDS.has(artifact.kind) ? (
            <ToolbarButton
              onClick={() => setShowIterate((v) => !v)}
              disabled={generating}
              icon={<Sparkles className="w-3.5 h-3.5" />}
              active={showIterate}
            >
              Iterate
            </ToolbarButton>
          ) : null}
          {versions.length > 1 ? (
            <VersionSwitcher
              versions={versions}
              active={activeVersion}
              current={detail?.current_version ?? artifact.version}
              onSelect={setActiveVersion}
            />
          ) : null}
        </div>

        {/* Iterate input */}
        {showIterate ? (
          <div className="px-4 py-2.5 border-b border-[#27272a]/60 bg-[#141417]">
            <div className="flex items-center gap-2">
              <input
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void onIterate();
                }}
                placeholder="Describe a change (e.g. add error handling)…"
                disabled={iterating}
                className="flex-1 px-3 py-1.5 text-[11.5px] bg-[#0d0d0f] border border-[#27272a] rounded-lg text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/40 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void onIterate()}
                disabled={iterating || instruction.trim() === ""}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all disabled:opacity-40 disabled:pointer-events-none"
              >
                {iterating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                {iterating ? "Revising…" : "Revise"}
              </button>
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="px-4 py-1.5 text-[10.5px] text-rose-400 bg-rose-500/5 border-b border-rose-500/10">
            {error}
          </p>
        ) : null}

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 min-h-[160px]">
          {generating ? (
            <Centered>
              <Loader2 className="w-7 h-7 animate-spin text-amber-400 mb-3" />
              <p className="text-[11px] text-zinc-400">Generating…</p>
            </Centered>
          ) : failed ? (
            <Centered>
              <Ban className="w-7 h-7 text-rose-400 mb-3" />
              <p className="text-[11px] text-zinc-400">Generation failed.</p>
            </Centered>
          ) : isText && loadingText ? (
            <Centered>
              <Loader2 className="w-6 h-6 animate-spin text-emerald-400/60" />
            </Centered>
          ) : isImage ? (
            imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imageUrl}
                alt={filename}
                className="max-w-full mx-auto rounded-lg border border-white/5"
              />
            ) : (
              <Centered>
                <Loader2 className="w-6 h-6 animate-spin text-emerald-400/60" />
              </Centered>
            )
          ) : (
            <ArtifactPreview kind={artifact.kind} content={isText ? text : null} />
          )}
        </div>
      </motion.div>
    </div>
  );
}

function ToolbarButton({
  onClick,
  disabled,
  icon,
  active,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  icon: React.ReactNode;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-lg border transition-all disabled:opacity-40 disabled:pointer-events-none ${
        active
          ? "text-emerald-300 bg-emerald-500/15 border-emerald-500/40"
          : "text-zinc-300 bg-[#27272a]/50 border-[#27272a] hover:bg-[#27272a]"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function VersionSwitcher({
  versions,
  active,
  current,
  onSelect,
}: {
  versions: ArtifactVersionDto[];
  active: number;
  current: number;
  onSelect: (version: number) => void;
}) {
  return (
    <div className="flex items-center gap-1 ml-auto">
      <History className="w-3 h-3 text-zinc-500" />
      {versions.map((v) => (
        <button
          key={v.version}
          type="button"
          onClick={() => onSelect(v.version)}
          title={v.version === current ? "current version" : `version ${v.version}`}
          className={`px-1.5 py-0.5 text-[10px] font-mono rounded border transition-all ${
            v.version === active
              ? "text-emerald-300 bg-emerald-500/15 border-emerald-500/40"
              : "text-zinc-400 bg-transparent border-[#27272a] hover:border-zinc-600"
          }`}
        >
          v{v.version}
          {v.version === current ? "•" : ""}
        </button>
      ))}
    </div>
  );
}

function StatusBadge({ generating, failed }: { generating: boolean; failed: boolean }) {
  if (generating) {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wide text-amber-300 bg-amber-500/10 border border-amber-500/20">
        <Loader2 className="w-2.5 h-2.5 animate-spin" /> Generating
      </span>
    );
  }
  if (failed) {
    return (
      <span className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wide text-rose-300 bg-rose-500/10 border border-rose-500/20">
        Failed
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wide text-emerald-300 bg-emerald-500/10 border border-emerald-500/20">
      Ready
    </span>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center py-10">
      {children}
    </div>
  );
}
