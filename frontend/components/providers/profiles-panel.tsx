"use client";

/**
 * Layer 3 — Inference Profiles (ARCH §9/§27). A profile bundles a default model
 * + inference params (temperature/top_p/max_tokens/reasoning/json_mode/streaming)
 * that agents reference. Lists `GET /providers/profiles` and creates new ones.
 * Numeric parsing/validation lives in the pure `provider-model` module.
 */
import { useState } from "react";
import { Trash2 } from "lucide-react";
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
import {
  useProfiles,
  useCatalog,
  useCreateProfile,
  useDeleteProfile,
} from "@/features/providers/use-providers";
import {
  initialProfileForm,
  validateProfile,
  toProfileCreate,
  parseInUseAgentNames,
  type ProfileFormState,
} from "@/features/providers/provider-model";
import { ApiError } from "@/lib/api/client";
import type { UUID } from "@/types/api";

/** The referencing-agent names from a profile-delete 409, or null for other errors. */
function inUseAgentNames(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  return parseInUseAgentNames(error.detail);
}

export function ProfilesPanel() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ProfileFormState>(initialProfileForm);
  const [error, setError] = useState<string | null>(null);

  const [deleteError, setDeleteError] = useState<string | null>(null);

  const profiles = useProfiles();
  const chatModels = useCatalog(); // any catalog model can be a profile default
  const create = useCreateProfile();
  const remove = useDeleteProfile();
  const patch = (next: Partial<ProfileFormState>) => setForm((p) => ({ ...p, ...next }));

  const onDelete = (id: UUID, name: string) => {
    if (!window.confirm(`Delete profile "${name}"?`)) return;
    setDeleteError(null);
    remove.mutate(id, {
      onError: (e) => {
        // 409: the profile is referenced by agents — name them so the user can reassign.
        const names = inUseAgentNames(e);
        setDeleteError(
          names && names.length > 0
            ? `"${name}" is in use by ${names.join(", ")}. Reassign those agents first.`
            : e.message,
        );
      },
    });
  };

  const submit = () => {
    const invalid = validateProfile(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    create.mutate(toProfileCreate(form), {
      onSuccess: () => {
        setForm(initialProfileForm());
        setOpen(false);
      },
      onError: (e) => setError(e.message),
    });
  };

  return (
    <Pane>
      <div className="flex items-center justify-between">
        <SectionTitle label="3 · Inference profiles" hint="Default model + params agents reference" />
        <GhostButton onClick={() => setOpen((v) => !v)}>{open ? "Close" : "Add profile"}</GhostButton>
      </div>

      {open ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 rounded-xl p-4 mb-4 bg-white/[0.02]">
          <Field label="Name">
            <TextInput value={form.name} onChange={(e) => patch({ name: e.target.value })} />
          </Field>
          <Field label="Default model">
            <SelectInput
              value={form.defaultModelId}
              onChange={(e) => patch({ defaultModelId: e.target.value })}
            >
              <option value="">None</option>
              {(chatModels.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Temperature" hint="0–2">
            <TextInput
              value={form.temperature}
              onChange={(e) => patch({ temperature: e.target.value })}
              inputMode="decimal"
              placeholder="0.7"
            />
          </Field>
          <Field label="top_p" hint="0–1">
            <TextInput
              value={form.topP}
              onChange={(e) => patch({ topP: e.target.value })}
              inputMode="decimal"
              placeholder="1.0"
            />
          </Field>
          <Field label="max_tokens">
            <TextInput
              value={form.maxTokens}
              onChange={(e) => patch({ maxTokens: e.target.value })}
              inputMode="numeric"
            />
          </Field>
          <Field label="Reasoning level" hint="e.g. low / medium / high">
            <TextInput
              value={form.reasoningLevel}
              onChange={(e) => patch({ reasoningLevel: e.target.value })}
            />
          </Field>
          <div className="flex flex-col gap-2 justify-center md:col-span-2">
            <Toggle checked={form.jsonMode} onChange={(on) => patch({ jsonMode: on })} label="JSON mode" />
            <Toggle checked={form.streaming} onChange={(on) => patch({ streaming: on })} label="Streaming" />
          </div>
          <div className="flex items-end justify-end md:col-span-2 gap-2">
            {error ? <p className="text-[11px] text-rose-400 font-mono mr-auto">{error}</p> : null}
            <PrimaryButton onClick={submit} loading={create.isPending}>
              Save profile
            </PrimaryButton>
          </div>
        </div>
      ) : null}

      <QueryBoundary
        isLoading={profiles.isLoading}
        error={profiles.error}
        data={profiles.data}
        isEmpty={(d) => d.length === 0}
        emptyMessage="No profiles yet — create one to assign models to agents."
      >
        {(list) => (
          <div className="flex flex-col gap-2">
            {deleteError ? (
              <p className="text-[11px] text-rose-400 font-mono">{deleteError}</p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {list.map((p) => (
                <li
                  key={p.id}
                  className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-2.5 flex items-center justify-between gap-3"
                >
                  <p className="text-[12.5px] font-semibold text-zinc-100 truncate">{p.name}</p>
                  <div className="flex items-center gap-2 shrink-0">
                    <p className="text-[10px] text-zinc-500 font-mono">
                      {p.temperature !== null ? `temp ${p.temperature}` : "temp —"}
                      {p.json_mode ? " · json" : ""}
                    </p>
                    <button
                      type="button"
                      title="Delete profile"
                      onClick={() => onDelete(p.id, p.name)}
                      disabled={remove.isPending}
                      className="p-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-400 hover:text-rose-400 hover:border-rose-500/30 transition-colors disabled:opacity-40"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </QueryBoundary>
    </Pane>
  );
}
