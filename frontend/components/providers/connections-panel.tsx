"use client";

/**
 * Layer 1 of the Model Resolution stack — provider Connections (ARCH §9.4).
 *
 * Bug 5: a created connection used to be stuck "pending" forever with no way to
 * validate it, and no edit/delete/test controls. This panel now exposes:
 *   - **Test** — runs the backend validation probe (ARCH §27.3); on success the
 *     pill flips to "ready", on failure the provider error is shown inline.
 *   - **Discover** — lists the provider's models into the catalog (ARCH §27.2),
 *     so they become selectable in chat / agents.
 *   - **Edit** / **Delete** — manage the connection.
 *
 * The API key is write-only: the backend never returns it. In local dev you may
 * paste the raw key (it is stored as the api_key_ref and resolved directly); in
 * production this field is a secrets-manager reference (ARCH §9.4).
 */
import { useState } from "react";
import { Pencil, Trash2, PlugZap, Download } from "lucide-react";
import {
  Pane,
  SectionTitle,
  Field,
  TextInput,
  SelectInput,
  PrimaryButton,
  GhostButton,
  QueryBoundary,
  StatusPill,
} from "@/components/crud/primitives";
import {
  useConnections,
  useCreateConnection,
  useUpdateConnection,
  useDeleteConnection,
  useTestConnection,
  useDiscoverConnection,
} from "@/features/providers/use-providers";
import {
  PROVIDER_OPTIONS,
  initialConnectionForm,
  connectionFormFromRead,
  providerNeedsBaseUrl,
  validateConnection,
  toConnectionCreate,
  toConnectionUpdate,
  type ConnectionFormState,
} from "@/features/providers/provider-model";
import type { ConnectionRead } from "@/types/api";

export function ConnectionsPanel() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ConnectionFormState>(initialConnectionForm);
  const [error, setError] = useState<string | null>(null);

  const connections = useConnections();
  const create = useCreateConnection();
  const patch = (next: Partial<ConnectionFormState>) => setForm((p) => ({ ...p, ...next }));

  const submit = () => {
    const invalid = validateConnection(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    create.mutate(toConnectionCreate(form), {
      onSuccess: () => {
        setForm(initialConnectionForm());
        setOpen(false);
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <Pane>
      <div className="flex items-center justify-between">
        <SectionTitle label="1 · Connections" hint="Provider endpoints + credentials" />
        <GhostButton onClick={() => setOpen((v) => !v)}>{open ? "Close" : "Add connection"}</GhostButton>
      </div>

      {open ? (
        <ConnectionForm
          form={form}
          patch={patch}
          error={error}
          loading={create.isPending}
          onSubmit={submit}
          submitLabel="Save connection"
        />
      ) : null}

      <QueryBoundary
        isLoading={connections.isLoading}
        error={connections.error}
        data={connections.data}
        isEmpty={(d) => d.length === 0}
        emptyMessage="No connections yet — add a provider to begin."
      >
        {(list) => (
          <ul className="flex flex-col gap-2">
            {list.map((c) => (
              <ConnectionRow key={c.id} connection={c} />
            ))}
          </ul>
        )}
      </QueryBoundary>
    </Pane>
  );
}

/** One connection card with Test / Discover / Edit / Delete (Bug 5). */
function ConnectionRow({ connection }: { connection: ConnectionRead }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ConnectionFormState>(() => connectionFormFromRead(connection));
  const [formError, setFormError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; message: string } | null>(null);

  const update = useUpdateConnection();
  const remove = useDeleteConnection();
  const test = useTestConnection();
  const discover = useDiscoverConnection();
  const patch = (next: Partial<ConnectionFormState>) => setForm((p) => ({ ...p, ...next }));
  const busy = test.isPending || discover.isPending || remove.isPending || update.isPending;

  const runTest = () => {
    setFeedback(null);
    test.mutate(connection.id, {
      onSuccess: (r) =>
        setFeedback({ ok: r.ok, message: r.ok ? `Validated — ${r.detail}` : r.detail }),
      onError: (e) => setFeedback({ ok: false, message: e.message }),
    });
  };

  const runDiscover = () => {
    setFeedback(null);
    discover.mutate(connection.id, {
      onSuccess: (models) =>
        setFeedback({ ok: true, message: `Discovered ${models.length} new model(s) into the catalog.` }),
      onError: (e) => setFeedback({ ok: false, message: e.message }),
    });
  };

  const runDelete = () => {
    if (!window.confirm(`Delete connection "${connection.display_name}"?`)) return;
    remove.mutate(connection.id, { onError: (e) => setFeedback({ ok: false, message: e.message }) });
  };

  const saveEdit = () => {
    const invalid = validateConnection(form);
    if (invalid) {
      setFormError(invalid);
      return;
    }
    setFormError(null);
    update.mutate(
      { id: connection.id, payload: toConnectionUpdate(form) },
      {
        onSuccess: () => {
          setEditing(false);
          setFeedback(null);
        },
        onError: (e) => setFormError(e.message),
      },
    );
  };

  return (
    <li className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-2.5 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold text-zinc-100 truncate">{connection.display_name}</p>
          <p className="text-[10px] text-zinc-500 font-mono">
            {connection.provider}
            {connection.base_url ? ` · ${connection.base_url}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <StatusPill status={connection.validated_at ? "ready" : "pending"} />
          <IconButton title="Test connection" onClick={runTest} disabled={busy}>
            <PlugZap className="w-3.5 h-3.5" />
          </IconButton>
          <IconButton title="Discover models" onClick={runDiscover} disabled={busy}>
            <Download className="w-3.5 h-3.5" />
          </IconButton>
          <IconButton title="Edit" onClick={() => setEditing((v) => !v)} disabled={busy}>
            <Pencil className="w-3.5 h-3.5" />
          </IconButton>
          <IconButton title="Delete" onClick={runDelete} disabled={busy} danger>
            <Trash2 className="w-3.5 h-3.5" />
          </IconButton>
        </div>
      </div>

      {test.isPending ? <p className="text-[11px] text-zinc-500 font-mono">Testing…</p> : null}
      {discover.isPending ? (
        <p className="text-[11px] text-zinc-500 font-mono">Discovering models…</p>
      ) : null}
      {feedback ? (
        <p
          className={`text-[11px] font-mono ${feedback.ok ? "text-emerald-400" : "text-rose-400"}`}
        >
          {feedback.message}
        </p>
      ) : null}

      {editing ? (
        <ConnectionForm
          form={form}
          patch={patch}
          error={formError}
          loading={update.isPending}
          onSubmit={saveEdit}
          submitLabel="Save changes"
        />
      ) : null}
    </li>
  );
}

/** Shared connection form (create + edit), driven by ConnectionFormState. */
function ConnectionForm({
  form,
  patch,
  error,
  loading,
  onSubmit,
  submitLabel,
}: {
  form: ConnectionFormState;
  patch: (next: Partial<ConnectionFormState>) => void;
  error: string | null;
  loading: boolean;
  onSubmit: () => void;
  submitLabel: string;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 rounded-xl p-4 my-3 bg-white/[0.02]">
      <Field label="Display name">
        <TextInput value={form.displayName} onChange={(e) => patch({ displayName: e.target.value })} />
      </Field>
      <Field label="Provider">
        <SelectInput
          value={form.provider}
          onChange={(e) => patch({ provider: e.target.value as ConnectionFormState["provider"] })}
        >
          {PROVIDER_OPTIONS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </SelectInput>
      </Field>
      <Field label={providerNeedsBaseUrl(form.provider) ? "Base URL (required)" : "Base URL (optional)"}>
        <TextInput
          value={form.baseUrl}
          onChange={(e) => patch({ baseUrl: e.target.value })}
          placeholder="https://…"
        />
      </Field>
      <Field label="API key" hint="Local dev: paste the raw key · Prod: a secrets-manager ref">
        <TextInput
          value={form.apiKeyRef}
          onChange={(e) => patch({ apiKeyRef: e.target.value })}
          placeholder="leave blank to keep the existing key"
        />
      </Field>
      <Field label="API version (Azure)">
        <TextInput value={form.apiVersion} onChange={(e) => patch({ apiVersion: e.target.value })} />
      </Field>
      <div className="flex items-end justify-end md:col-span-2 gap-2">
        {error ? <p className="text-[11px] text-rose-400 font-mono mr-auto">{error}</p> : null}
        <PrimaryButton onClick={onSubmit} loading={loading}>
          {submitLabel}
        </PrimaryButton>
      </div>
    </div>
  );
}

function IconButton({
  children,
  title,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`p-1.5 rounded-lg border border-white/10 bg-white/[0.02] transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        danger
          ? "text-zinc-400 hover:text-rose-400 hover:border-rose-500/30"
          : "text-zinc-400 hover:text-emerald-400 hover:border-emerald-500/30"
      }`}
    >
      {children}
    </button>
  );
}
