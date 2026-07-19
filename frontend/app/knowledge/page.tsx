"use client";

/**
 * Knowledge Base (ITEM 2, ARCH §10.5).
 *
 * Pick a team → set its runtime embedding model → add RAG sources. The Kind selector
 * drives the input: URL → a URI field; File → a real drag/drop + picker upload (any
 * extension); Database → DSN + query. Sources show live status (pending → ingesting →
 * ready/failed), chunk_count, and the failure reason; the list polls until terminal.
 * Each source has a delete control (removes it + its vector chunks).
 */
import { useRef, useState } from "react";
import { Database, Trash2, Upload } from "lucide-react";
import {
  CrudPage,
  Pane,
  Field,
  TextInput,
  SelectInput,
  PrimaryButton,
  GhostButton,
  QueryBoundary,
  StatusPill,
  EmptyState,
} from "@/components/crud/primitives";
import { TeamPicker, AgentPicker } from "@/components/crud/resource-pickers";
import {
  useKnowledge,
  useRegisterSource,
  useUploadKnowledgeFile,
  useDeleteKnowledgeSource,
} from "@/features/knowledge/use-knowledge";
import { TeamEmbeddingPicker } from "@/components/knowledge/team-embedding-picker";
import type { KnowledgeKind, KnowledgeSourceRead } from "@/types/api";

const KINDS: readonly { value: KnowledgeKind; label: string }[] = [
  { value: "file", label: "File (any type)" },
  { value: "url", label: "URL" },
  { value: "db", label: "Database" },
  { value: "team_doc", label: "Team doc" },
];

export default function KnowledgePage() {
  const [teamId, setTeamId] = useState("");
  const [kind, setKind] = useState<KnowledgeKind>("file");
  const [uri, setUri] = useState("");
  const [dsn, setDsn] = useState("");
  const [dbQuery, setDbQuery] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sources = useKnowledge(teamId || null);
  const register = useRegisterSource();
  const upload = useUploadKnowledgeFile();

  const reset = () => {
    setUri("");
    setDsn("");
    setDbQuery("");
    setDisplayName("");
    setFile(null);
  };

  const submit = () => {
    if (!teamId) {
      setError("Pick a team first.");
      return;
    }
    setError(null);
    if (kind === "file") {
      if (!file) {
        setError("Choose a file to upload.");
        return;
      }
      upload.mutate(
        { teamId, file, agentId: agentId || null, displayName: displayName.trim() || null },
        { onSuccess: reset, onError: (e) => setError(e.message) },
      );
      return;
    }
    if (kind === "db" && (!dsn.trim() || !dbQuery.trim())) {
      setError("Database sources need a DSN and a SELECT query.");
      return;
    }
    register.mutate(
      {
        teamId,
        payload: {
          kind,
          uri: kind === "db" ? null : uri.trim() || null,
          display_name: displayName.trim() || null,
          agent_id: agentId || null,
          connector_config:
            kind === "db" ? { dsn: dsn.trim(), query: dbQuery.trim() } : null,
        },
      },
      { onSuccess: reset, onError: (e) => setError(e.message) },
    );
  };

  const busy = register.isPending || upload.isPending;

  return (
    <CrudPage
      eyebrow="ITEM 2 · Knowledge"
      title="Knowledge Base"
      description="Upload any document or register a URL/database. Ingestion runs on a worker — sources move pending → ingesting → ready with a live chunk count, or failed with a reason."
    >
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5">
        <Pane>
          <TeamPicker value={teamId} onChange={setTeamId} />
          {teamId ? <TeamEmbeddingPicker teamId={teamId} /> : null}

          <div className="flex flex-col gap-3 mt-3">
            <Field label="Kind">
              <SelectInput value={kind} onChange={(e) => setKind(e.target.value as KnowledgeKind)}>
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </SelectInput>
            </Field>

            <KindInput
              kind={kind}
              uri={uri}
              onUri={setUri}
              dsn={dsn}
              onDsn={setDsn}
              dbQuery={dbQuery}
              onDbQuery={setDbQuery}
              file={file}
              onFile={setFile}
            />

            <Field label="Display name">
              <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </Field>
            <AgentPicker
              teamId={teamId || null}
              value={agentId}
              onChange={setAgentId}
              label="Scope"
              allLabel="Team-shared (all agents)"
            />
            {error ? <p className="text-[11px] text-rose-400 font-mono">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <GhostButton onClick={reset}>Clear</GhostButton>
              <PrimaryButton onClick={submit} loading={busy} disabled={!teamId}>
                {kind === "file" ? "Upload + ingest" : "Register source"}
              </PrimaryButton>
            </div>
          </div>
        </Pane>

        <Pane>
          {teamId ? (
            <QueryBoundary
              isLoading={sources.isLoading}
              error={sources.error}
              data={sources.data}
              isEmpty={(d) => d.length === 0}
              emptyMessage="No sources for this team yet — upload a file or register a URL."
            >
              {(list) => (
                <ul className="flex flex-col gap-2">
                  {list.map((s) => (
                    <SourceRow key={s.id} source={s} teamId={teamId} />
                  ))}
                </ul>
              )}
            </QueryBoundary>
          ) : (
            <EmptyState
              message="Pick a team to view its knowledge sources."
              icon={<Database className="w-7 h-7" />}
            />
          )}
        </Pane>
      </div>
    </CrudPage>
  );
}

/** The Kind selector drives this input (ARCH §10.5: URL/File/DB/team_doc). */
function KindInput({
  kind,
  uri,
  onUri,
  dsn,
  onDsn,
  dbQuery,
  onDbQuery,
  file,
  onFile,
}: {
  kind: KnowledgeKind;
  uri: string;
  onUri: (v: string) => void;
  dsn: string;
  onDsn: (v: string) => void;
  dbQuery: string;
  onDbQuery: (v: string) => void;
  file: File | null;
  onFile: (f: File | null) => void;
}) {
  if (kind === "file") {
    return <FileDrop file={file} onFile={onFile} />;
  }
  if (kind === "db") {
    return (
      <div className="flex flex-col gap-3">
        <Field label="DSN" hint="Read-only connection string (SELECT runs in a read-only txn)">
          <TextInput
            value={dsn}
            onChange={(e) => onDsn(e.target.value)}
            placeholder="postgresql://user:pass@host:5432/db"
          />
        </Field>
        <Field label="SELECT query" hint="A single read-only SELECT; rows become chunks">
          <TextInput
            value={dbQuery}
            onChange={(e) => onDbQuery(e.target.value)}
            placeholder="SELECT id, title, body FROM articles"
          />
        </Field>
      </div>
    );
  }
  if (kind === "team_doc") {
    return (
      <Field label="Reference">
        <TextInput value={uri} onChange={(e) => onUri(e.target.value)} placeholder="doc reference" />
      </Field>
    );
  }
  return (
    <Field label="URL">
      <TextInput value={uri} onChange={(e) => onUri(e.target.value)} placeholder="https://…" />
    </Field>
  );
}

/** Drag/drop + picker file control (real upload, any extension). */
function FileDrop({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <Field label="File" hint="Any type — pdf, docx, xlsx, csv, md, images…">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (e.dataTransfer.files?.[0]) onFile(e.dataTransfer.files[0]);
        }}
        className={`w-full flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center transition-colors ${
          over ? "border-violet-400/60 bg-violet-500/[0.06]" : "border-white/15 bg-white/[0.02]"
        }`}
      >
        <Upload className="w-5 h-5 text-zinc-400" />
        <span className="text-[12px] text-zinc-300">
          {file ? file.name : "Drag a file here, or click to choose"}
        </span>
        {file ? (
          <span className="text-[10px] text-zinc-500 font-mono">{(file.size / 1024).toFixed(1)} KB</span>
        ) : null}
      </button>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </Field>
  );
}

function SourceRow({ source, teamId }: { source: KnowledgeSourceRead; teamId: string }) {
  const remove = useDeleteKnowledgeSource();
  return (
    <li className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold text-zinc-100 truncate">
          {source.display_name ?? source.uri ?? source.kind}
        </p>
        <p className="text-[10px] text-zinc-500 font-mono truncate">
          {source.kind}
          {source.agent_id ? " · agent-private" : " · team-shared"} · {source.chunk_count} chunks
        </p>
        {source.status === "failed" && source.error ? (
          <p className="text-[10px] text-rose-400/90 font-mono truncate mt-0.5" title={source.error}>
            {source.error}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <StatusPill status={source.status} />
        <button
          type="button"
          title="Delete source"
          onClick={() => {
            if (window.confirm(`Delete "${source.display_name ?? source.kind}" and its chunks?`))
              remove.mutate({ teamId, sourceId: source.id });
          }}
          disabled={remove.isPending}
          className="p-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-400 hover:text-rose-400 hover:border-rose-500/30 transition-colors disabled:opacity-40"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </li>
  );
}
