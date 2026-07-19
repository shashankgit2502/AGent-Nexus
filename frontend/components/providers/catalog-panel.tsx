"use client";

/**
 * Layer 2 — the model Catalog (ARCH §9.3), as a master-detail (ITEM 1).
 *
 * MASTER = the connections; DETAIL = each connection's models, lazily loaded and
 * searchable (`ConnectionModelsList`). This replaces the old flat list that
 * rendered every model across every connection in one scroll. Manual model
 * registration (`POST /providers/catalog`) stays here as the "Add model" form;
 * `supports_tools` is the §9.3 hard gate for mesh agents.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import {
  Pane,
  SectionTitle,
  Field,
  TextInput,
  SelectInput,
  Toggle,
  PrimaryButton,
  GhostButton,
  QueryBoundary,
} from "@/components/crud/primitives";
import { ConnectionModelsList } from "@/components/providers/connection-models-list";
import {
  useConnections,
  useCreateCatalogModel,
  useDeleteConnection,
} from "@/features/providers/use-providers";
import {
  initialCatalogForm,
  validateCatalog,
  toCatalogCreate,
  type CatalogFormState,
} from "@/features/providers/provider-model";
import type { ConnectionRead, ModelType } from "@/types/api";

export function CatalogPanel() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CatalogFormState>(initialCatalogForm);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const connections = useConnections();
  const create = useCreateCatalogModel();
  const patch = (next: Partial<CatalogFormState>) => setForm((p) => ({ ...p, ...next }));
  const isChat = form.modelType === "chat";

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = () => {
    const invalid = validateCatalog(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    create.mutate(toCatalogCreate(form), {
      onSuccess: () => {
        setForm(initialCatalogForm());
        setOpen(false);
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <Pane>
      <div className="flex items-center justify-between">
        <SectionTitle label="2 · Catalog" hint="Models grouped by connection · supports_tools gate" />
        <GhostButton onClick={() => setOpen((v) => !v)}>{open ? "Close" : "Add model"}</GhostButton>
      </div>

      {open ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 rounded-xl p-4 mb-4 bg-white/[0.02]">
          <Field label="Connection">
            <SelectInput
              value={form.providerConnectionId}
              onChange={(e) => patch({ providerConnectionId: e.target.value })}
            >
              <option value="">Select a connection…</option>
              {(connections.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Model type">
            <SelectInput
              value={form.modelType}
              onChange={(e) => patch({ modelType: e.target.value as ModelType })}
            >
              <option value="chat">chat</option>
              <option value="embedding">embedding</option>
            </SelectInput>
          </Field>
          <Field label="Display name">
            <TextInput value={form.displayName} onChange={(e) => patch({ displayName: e.target.value })} />
          </Field>
          <Field label="Model identifier" hint="Provider's model id">
            <TextInput
              value={form.modelIdentifier}
              onChange={(e) => patch({ modelIdentifier: e.target.value })}
              placeholder="gpt-4o, claude-opus-4-8, …"
            />
          </Field>
          <Field label="Context window">
            <TextInput
              value={form.contextWindow}
              onChange={(e) => patch({ contextWindow: e.target.value })}
              inputMode="numeric"
              placeholder="128000"
            />
          </Field>
          <div className="flex flex-col gap-2 justify-center">
            {isChat ? (
              <Toggle
                checked={form.supportsTools}
                onChange={(on) => patch({ supportsTools: on })}
                label="supports_tools"
                hint="Required for mesh agents"
              />
            ) : (
              <p className="text-[10.5px] text-zinc-600">Embeddings are not tool-callers.</p>
            )}
            <Toggle
              checked={form.supportsStreaming}
              onChange={(on) => patch({ supportsStreaming: on })}
              label="supports_streaming"
            />
          </div>
          <div className="flex items-end justify-end md:col-span-2 gap-2">
            {error ? <p className="text-[11px] text-rose-400 font-mono mr-auto">{error}</p> : null}
            <PrimaryButton onClick={submit} loading={create.isPending}>
              Save model
            </PrimaryButton>
          </div>
        </div>
      ) : null}

      <QueryBoundary
        isLoading={connections.isLoading}
        error={connections.error}
        data={connections.data}
        isEmpty={(d) => d.length === 0}
        emptyMessage="No connections yet — register one above to add models."
      >
        {(list) => (
          <ul className="flex flex-col gap-2">
            {list.map((c) => (
              <ConnectionRow
                key={c.id}
                connection={c}
                expanded={expanded.has(c.id)}
                onToggle={() => toggle(c.id)}
              />
            ))}
          </ul>
        )}
      </QueryBoundary>
    </Pane>
  );
}

/** One master row: a connection header that expands to reveal its models, with a
 * delete control (the expand toggle and delete are sibling buttons — a delete
 * `<button>` must not nest inside the expand `<button>`). */
function ConnectionRow({
  connection,
  expanded,
  onToggle,
}: {
  connection: ConnectionRead;
  expanded: boolean;
  onToggle: () => void;
}) {
  const remove = useDeleteConnection();

  return (
    <li className="rounded-lg border border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="flex items-center gap-2 min-w-0 flex-1 text-left"
        >
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-zinc-400 shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-zinc-400 shrink-0" />
          )}
          <span className="text-[12.5px] font-semibold text-zinc-100 truncate">
            {connection.display_name}
          </span>
        </button>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-400 border border-white/10 rounded px-1.5 py-0.5">
            {connection.provider}
          </span>
          <button
            type="button"
            title="Delete connection"
            onClick={() => {
              if (window.confirm(`Delete connection "${connection.display_name}" and hide its models?`))
                remove.mutate(connection.id);
            }}
            disabled={remove.isPending}
            className="p-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-400 hover:text-rose-400 hover:border-rose-500/30 transition-colors disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {expanded ? (
        <div className="px-4 pb-4 border-t border-white/[0.06]">
          <ConnectionModelsList connectionId={connection.id} active={expanded} />
        </div>
      ) : null}
    </li>
  );
}
