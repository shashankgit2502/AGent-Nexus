"use client";

/**
 * TeamFormDialog — create or edit a team (ARCH §14 `POST /teams` / `PUT /teams/{id}`).
 *
 * Captures the collaboration goal (title/description/success criteria) the
 * orchestrator uses to seed the mesh. With no `team` it posts a new team; given a
 * `team` it pre-fills the fields and PUTs a partial update — mirroring the
 * create/edit duality of `AgentFormDialog`. `CreateTeamDialog` is kept as a thin
 * create-only alias for back-compat.
 */
import { useState } from "react";
import { X } from "lucide-react";
import { useCreateTeam, useUpdateTeam } from "@/features/teams/use-teams";
import { Field, TextInput, TextArea, PrimaryButton, GhostButton } from "@/components/crud/primitives";
import type { TeamCreate, TeamRead, TeamUpdate } from "@/types/api";

interface TeamFormDialogProps {
  /** When set, the dialog edits this team; otherwise it creates a new one. */
  team?: TeamRead;
  onClose: () => void;
  onSaved: (team: TeamRead) => void;
}

export function TeamFormDialog({ team, onClose, onSaved }: TeamFormDialogProps) {
  const isEdit = team !== undefined;
  const [name, setName] = useState(team?.name ?? "");
  const [description, setDescription] = useState(team?.description ?? "");
  const [goalTitle, setGoalTitle] = useState(team?.goal_title ?? "");
  const [goalDescription, setGoalDescription] = useState(team?.goal_description ?? "");
  const [criteria, setCriteria] = useState((team?.success_criteria ?? []).join("\n"));
  const [error, setError] = useState<string | null>(null);

  const create = useCreateTeam();
  const update = useUpdateTeam();
  const pending = create.isPending || update.isPending;

  const submit = () => {
    if (!name.trim()) {
      setError("Name the team.");
      return;
    }
    setError(null);
    const fields = {
      name: name.trim(),
      description: description.trim() || null,
      goal_title: goalTitle.trim() || null,
      goal_description: goalDescription.trim() || null,
      success_criteria: criteria
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    };

    const onError = (e: Error) => setError(e.message);
    if (isEdit) {
      const payload: TeamUpdate = fields;
      update.mutate({ teamId: team.id, payload }, { onSuccess: onSaved, onError });
    } else {
      const payload: TeamCreate = fields;
      create.mutate(payload, { onSuccess: onSaved, onError });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="artistic-pane w-full max-w-md rounded-2xl border border-white/10 p-5 flex flex-col gap-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-zinc-100">{isEdit ? "Edit team" : "New team"}</h3>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Research Mesh" />
        </Field>
        <Field label="Description">
          <TextArea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this team is for…"
          />
        </Field>
        <Field label="Goal title">
          <TextInput value={goalTitle} onChange={(e) => setGoalTitle(e.target.value)} />
        </Field>
        <Field label="Goal description">
          <TextArea value={goalDescription} onChange={(e) => setGoalDescription(e.target.value)} />
        </Field>
        <Field label="Success criteria" hint="One per line">
          <TextArea
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            placeholder={"Cites sources\nNo open questions"}
          />
        </Field>

        {error ? <p className="text-[11px] text-rose-400 font-mono">{error}</p> : null}

        <div className="flex justify-end gap-2">
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={submit} loading={pending}>
            {isEdit ? "Save changes" : "Create team"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

interface CreateTeamDialogProps {
  onClose: () => void;
  onCreated: (team: TeamRead) => void;
}

/** Back-compat create-only alias around {@link TeamFormDialog}. */
export function CreateTeamDialog({ onClose, onCreated }: CreateTeamDialogProps) {
  return <TeamFormDialog onClose={onClose} onSaved={onCreated} />;
}
