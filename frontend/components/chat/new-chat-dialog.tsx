"use client";

/**
 * NewChatDialog (§9A.1) — pick a target before opening a chat:
 *  - **Team** (multi-agent): choose a team; optionally mark it a Playground
 *    (ephemeral, excluded from history).
 *  - **No team** (single LLM): choose an inference profile (required) + optional
 *    catalog model override → the `{profile_id, model_id?}` model_ref (ARCH §8.5.5).
 *
 * Client-side validation mirrors the backend `ConversationCreate` validator
 * (R5 — fail fast at the boundary) before `POST /conversations`.
 */
import { useState } from "react";
import { X, Users, Bot, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTeams } from "@/features/sessions/use-run-controls";
import { useCreateConversation, useProfiles, useChatCatalog } from "@/features/chat/use-chat";
import {
  validateNewChat,
  toConversationCreate,
  type NewChatInput,
} from "@/features/chat/chat-model";
import { SelectInput } from "@/components/crud/primitives";
import type { ConversationRead } from "@/types/api";

interface NewChatDialogProps {
  onClose: () => void;
  onCreated: (conversation: ConversationRead) => void;
}

type Tab = "team" | "no-team";

export function NewChatDialog({ onClose, onCreated }: NewChatDialogProps) {
  const [tab, setTab] = useState<Tab>("team");
  const [teamId, setTeamId] = useState("");
  const [isPlayground, setIsPlayground] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [modelId, setModelId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const teams = useTeams();
  const profiles = useProfiles();
  const catalog = useChatCatalog();
  const create = useCreateConversation();

  const submit = () => {
    const input: NewChatInput =
      tab === "team"
        ? { kind: "team", teamId, isPlayground }
        : { kind: "no-team", profileId, modelId: modelId || null };
    const invalid = validateNewChat(input);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    create.mutate(toConversationCreate(input), {
      onSuccess: onCreated,
      onError: (e) => setError(e.message),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="artistic-pane w-full max-w-md rounded-2xl border border-white/10 p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-zinc-100">New chat</h3>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <TabButton active={tab === "team"} onClick={() => setTab("team")} icon={<Users className="w-3.5 h-3.5" />} label="Team" />
          <TabButton active={tab === "no-team"} onClick={() => setTab("no-team")} icon={<Bot className="w-3.5 h-3.5" />} label="No team (LLM)" />
        </div>

        {tab === "team" ? (
          <div className="flex flex-col gap-3">
            <Field label="Team">
              <SelectInput value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">Select a team…</option>
                {(teams.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <label className="inline-flex items-center gap-2 text-[11px] text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={isPlayground}
                onChange={(e) => setIsPlayground(e.target.checked)}
                className="accent-emerald-500"
              />
              Playground (ephemeral — not saved to history)
            </label>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <Field label="Inference profile (required)">
              <SelectInput value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                <option value="">Select a profile…</option>
                {(profiles.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Model override (optional)">
              <SelectInput value={modelId} onChange={(e) => setModelId(e.target.value)}>
                <option value="">Use profile default</option>
                {(catalog.data ?? [])
                  .filter((m) => m.model_type === "chat")
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name}
                    </option>
                  ))}
              </SelectInput>
            </Field>
          </div>
        )}

        {error ? <p className="text-[11px] text-rose-400 font-mono">{error}</p> : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-[11px] text-zinc-400 hover:text-zinc-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={create.isPending}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[11px] font-semibold transition-colors disabled:opacity-50"
          >
            {create.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Start chat
          </button>
        </div>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-semibold border transition-colors",
        active
          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
          : "bg-white/[0.02] border-white/10 text-zinc-400 hover:text-zinc-200",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[9.5px] font-mono uppercase tracking-[0.2em] text-zinc-500">{label}</span>
      {children}
    </div>
  );
}
