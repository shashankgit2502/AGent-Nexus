"use client";

/**
 * AgentFormDialog — create or edit a peer ReAct agent (ARCH §22). Persona
 * (name/description/instructions), the five real capability toggles
 * (agent-model `CAPABILITY_CATALOG`), memory flag, and the model selection
 * (inference profile + optional override model). All form↔DTO mapping lives in
 * the pure `agent-model` module; this is a thin state wrapper.
 *
 * The override model picker is filtered to `supports_tools` — mesh agents must
 * be tool-callers (ARCH §9.3 hard gate).
 */
import { useMemo, useState } from "react";
import { X, Unplug } from "lucide-react";
import {
  Field,
  TextInput,
  TextArea,
  SelectInput,
  Toggle,
  PrimaryButton,
  GhostButton,
} from "@/components/crud/primitives";
import { useProfiles, useCatalog } from "@/features/providers/use-providers";
import { useCreateAgent, useUpdateAgent } from "@/features/agents/use-agents";
import {
  CAPABILITY_CATALOG,
  initialAgentForm,
  toggleCapability,
  isCapabilityOn,
  validateAgentForm,
  toAgentCreate,
  toAgentUpdate,
  toolCapabilityWarning,
  type AgentFormState,
  type ModelCapabilityLookup,
} from "@/features/agents/agent-model";
import type { AgentRead } from "@/types/api";

interface AgentFormDialogProps {
  teamId: string;
  /** Present ⇒ edit mode; absent ⇒ create mode. */
  agent?: AgentRead;
  onClose: () => void;
  onSaved: () => void;
}

export function AgentFormDialog({ teamId, agent, onClose, onSaved }: AgentFormDialogProps) {
  const [form, setForm] = useState<AgentFormState>(() => initialAgentForm(agent));
  const [error, setError] = useState<string | null>(null);

  const profiles = useProfiles();
  const models = useCatalog(); // full catalog: powers the override picker AND the §9.3 pre-check
  const create = useCreateAgent();
  const update = useUpdateAgent();
  const pending = create.isPending || update.isPending;

  // Tool-capable subset for the override picker (mesh agents must be tool-callers, §9.3).
  const toolModels = useMemo(
    () => (models.data ?? []).filter((m) => m.supports_tools),
    [models.data],
  );

  // Capability facts joined from profiles + catalog, so the form can warn when the chosen
  // profile's default model (or override) can't call tools — closing the config-time hole
  // that let nemotron-backed agents be created (the override picker is already filtered,
  // but the profile dropdown lists every profile regardless of its model).
  const lookup = useMemo<ModelCapabilityLookup>(() => {
    const profileDefault = new Map(
      (profiles.data ?? []).map((p) => [p.id, p.default_model_id ?? null] as const),
    );
    const supports = new Map((models.data ?? []).map((m) => [m.id, m.supports_tools] as const));
    return {
      profileDefaultModelId: (id) => profileDefault.get(id),
      modelSupportsTools: (id) => supports.get(id),
    };
  }, [profiles.data, models.data]);
  const capabilityWarning = toolCapabilityWarning(form, lookup);

  const patch = (next: Partial<AgentFormState>) => setForm((prev) => ({ ...prev, ...next }));

  const submit = () => {
    const invalid = validateAgentForm(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    // Mirror the backend 422: don't even round-trip a model that can't call tools.
    if (capabilityWarning) {
      setError(capabilityWarning);
      return;
    }
    setError(null);
    const onError = (e: Error) => setError(e.message);
    if (agent) {
      update.mutate(
        { teamId, agentId: agent.id, payload: toAgentUpdate(form) },
        { onSuccess: onSaved, onError },
      );
    } else {
      create.mutate({ teamId, payload: toAgentCreate(form) }, { onSuccess: onSaved, onError });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="artistic-pane w-full max-w-lg rounded-2xl border border-white/10 p-5 flex flex-col gap-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-zinc-100">{agent ? "Edit agent" : "New agent"}</h3>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <Field label="Name">
          <TextInput value={form.name} onChange={(e) => patch({ name: e.target.value })} placeholder="Critic" />
        </Field>
        <Field label="Description">
          <TextInput
            value={form.description}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder="Pokes holes in proposals"
          />
        </Field>
        <Field label="Instructions" hint="The agent's persona / system prompt">
          <TextArea
            value={form.instructions}
            onChange={(e) => patch({ instructions: e.target.value })}
          />
        </Field>

        <div className="flex flex-col gap-2.5">
          <span className="text-[9.5px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            Capabilities
          </span>
          {CAPABILITY_CATALOG.map((cap) => (
            <Toggle
              key={cap.key}
              checked={isCapabilityOn(form.capabilities, cap.key)}
              onChange={(on) => patch({ capabilities: toggleCapability(form.capabilities, cap.key, on) })}
              label={cap.label}
              hint={cap.hint}
            />
          ))}
        </div>

        <Toggle
          checked={form.memoryEnabled}
          onChange={(on) => patch({ memoryEnabled: on })}
          label="Long-term memory"
          hint="Persist private / shared memory across sessions"
        />

        <div className="grid grid-cols-2 gap-3">
          <Field label="Inference profile" hint="Required — provides the agent's model">
            <SelectInput value={form.profileId} onChange={(e) => patch({ profileId: e.target.value })}>
              <option value="">Select a profile…</option>
              {(profiles.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Override model" hint="Tool-capable only">
            <SelectInput
              value={form.overrideModelId}
              onChange={(e) => patch({ overrideModelId: e.target.value })}
            >
              <option value="">Use profile default</option>
              {toolModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </SelectInput>
          </Field>
        </div>

        {capabilityWarning ? (
          <p className="text-[11px] text-amber-400 font-mono flex items-start gap-1.5">
            <Unplug className="w-3.5 h-3.5 shrink-0 mt-px" />
            <span>{capabilityWarning}</span>
          </p>
        ) : null}
        {error ? <p className="text-[11px] text-rose-400 font-mono">{error}</p> : null}

        <div className="flex justify-end gap-2">
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={submit} loading={pending} disabled={capabilityWarning !== null}>
            {agent ? "Save changes" : "Create agent"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}
