"use client";

/**
 * Controlled resource pickers reused by Knowledge + Memory (and anywhere a
 * screen scopes by team / agent). They wrap the shared `useTeams` / `useTeamAgents`
 * React Query reads so the screens stay declarative. Selection state is owned by
 * the parent (controlled) — these only render options.
 */
import { Field, SelectInput } from "@/components/crud/primitives";
import { useTeams } from "@/features/teams/use-teams";
import { useTeamAgents } from "@/features/agents/use-agents";

interface TeamPickerProps {
  value: string;
  onChange: (teamId: string) => void;
  label?: string;
}

export function TeamPicker({ value, onChange, label = "Team" }: TeamPickerProps) {
  const teams = useTeams();
  return (
    <Field label={label}>
      <SelectInput value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a team…</option>
        {(teams.data ?? []).map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </SelectInput>
    </Field>
  );
}

interface AgentPickerProps {
  teamId: string | null;
  value: string;
  onChange: (agentId: string) => void;
  label?: string;
  /** Label for the "no selection" option (e.g. team-shared scope). */
  allLabel?: string;
}

export function AgentPicker({ teamId, value, onChange, label = "Agent", allLabel }: AgentPickerProps) {
  const agents = useTeamAgents(teamId);
  return (
    <Field label={label}>
      <SelectInput
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={!teamId}
      >
        <option value="">{allLabel ?? "Select an agent…"}</option>
        {(agents.data ?? []).map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </SelectInput>
    </Field>
  );
}
