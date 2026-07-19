"use client";

/**
 * Teams + Agent Builder (Slice 4, ARCH §14/§22).
 *
 * Master-detail: the left rail lists org teams (`GET /teams`) with a create
 * action; selecting one loads its roster (`GET /teams/{id}/agents`) on the right
 * with add / edit / delete. All reads/writes are React Query (REST DTOs); the
 * pure form→DTO mapping lives in `agent-model`. Reference glass theme preserved.
 */
import { useState } from "react";
import { Pencil, Trash2, Bot } from "lucide-react";
import {
  CrudPage,
  Pane,
  AddButton,
  GhostButton,
  EmptyState,
  QueryBoundary,
  StatusPill,
} from "@/components/crud/primitives";
import { cn } from "@/lib/utils";
import { useTeams, useDeleteTeam } from "@/features/teams/use-teams";
import { useTeamAgents, useDeleteAgent } from "@/features/agents/use-agents";
import { capabilitySummary } from "@/features/agents/agent-model";
import { TeamFormDialog } from "@/components/teams/create-team-dialog";
import { AgentFormDialog } from "@/components/teams/agent-form-dialog";
import type { TeamRead, AgentRead } from "@/types/api";

export default function TeamsPage() {
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [teamDialog, setTeamDialog] = useState<{ team?: TeamRead } | null>(null);
  const [agentDialog, setAgentDialog] = useState<{ agent?: AgentRead } | null>(null);

  const teams = useTeams();
  const removeTeam = useDeleteTeam();

  const onDeleteTeam = (team: TeamRead) => {
    if (!window.confirm(`Delete team "${team.name}"? Its agents and sessions are removed too.`))
      return;
    removeTeam.mutate(team.id, {
      onSuccess: () => {
        if (selectedTeamId === team.id) setSelectedTeamId(null);
      },
    });
  };

  return (
    <CrudPage
      eyebrow="Slice 4 · CRUD"
      title="Teams Builder"
      description="Create teams and configure peer ReAct agents — personas, capabilities, profile and model overrides."
      action={<AddButton onClick={() => setTeamDialog({})}>New team</AddButton>}
    >
      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-5">
        {/* Teams rail */}
        <Pane className="p-3">
          <QueryBoundary
            isLoading={teams.isLoading}
            error={teams.error}
            data={teams.data}
            isEmpty={(d) => d.length === 0}
            emptyMessage="No teams yet — create your first team."
          >
            {(list) => (
              <ul className="flex flex-col gap-1">
                {list.map((team) => (
                  <TeamRow
                    key={team.id}
                    team={team}
                    active={team.id === selectedTeamId}
                    onSelect={() => setSelectedTeamId(team.id)}
                    onEdit={() => setTeamDialog({ team })}
                    onDelete={() => onDeleteTeam(team)}
                    deleting={removeTeam.isPending}
                  />
                ))}
              </ul>
            )}
          </QueryBoundary>
        </Pane>

        {/* Roster */}
        <Pane>
          {selectedTeamId ? (
            <AgentRoster
              teamId={selectedTeamId}
              onAdd={() => setAgentDialog({})}
              onEdit={(agent) => setAgentDialog({ agent })}
            />
          ) : (
            <EmptyState message="Select a team to manage its agents." icon={<Bot className="w-7 h-7" />} />
          )}
        </Pane>
      </div>

      {teamDialog ? (
        <TeamFormDialog
          team={teamDialog.team}
          onClose={() => setTeamDialog(null)}
          onSaved={(team) => {
            setTeamDialog(null);
            setSelectedTeamId(team.id);
          }}
        />
      ) : null}

      {agentDialog && selectedTeamId ? (
        <AgentFormDialog
          teamId={selectedTeamId}
          agent={agentDialog.agent}
          onClose={() => setAgentDialog(null)}
          onSaved={() => setAgentDialog(null)}
        />
      ) : null}
    </CrudPage>
  );
}

function TeamRow({
  team,
  active,
  onSelect,
  onEdit,
  onDelete,
  deleting,
}: {
  team: TeamRead;
  active: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <li
      className={cn(
        "group relative rounded-lg border transition-colors",
        active
          ? "bg-emerald-500/10 border-emerald-500/30"
          : "bg-white/[0.02] border-white/10 hover:bg-white/5",
      )}
    >
      <button type="button" onClick={onSelect} className="w-full text-left px-3 py-2.5 pr-16">
        <p className="text-[12.5px] font-semibold text-zinc-100 truncate">{team.name}</p>
        {team.goal_title ? (
          <p className="text-[10.5px] text-zinc-500 truncate mt-0.5">{team.goal_title}</p>
        ) : null}
      </button>
      {/* Edit / delete — revealed on hover/focus so the rail stays clean. */}
      <div className="absolute top-1.5 right-1.5 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={onEdit}
          title="Edit team"
          aria-label={`Edit team ${team.name}`}
          className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-white/10 transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          title="Delete team"
          aria-label={`Delete team ${team.name}`}
          className="p-1.5 rounded-md text-zinc-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </li>
  );
}

function AgentRoster({
  teamId,
  onAdd,
  onEdit,
}: {
  teamId: string;
  onAdd: () => void;
  onEdit: (agent: AgentRead) => void;
}) {
  const agents = useTeamAgents(teamId);
  const remove = useDeleteAgent();

  const onDelete = (agent: AgentRead) => {
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return;
    remove.mutate({ teamId, agentId: agent.id });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-100">Agents</h2>
        <AddButton onClick={onAdd}>Add agent</AddButton>
      </div>

      <QueryBoundary
        isLoading={agents.isLoading}
        error={agents.error}
        data={agents.data}
        isEmpty={(d) => d.length === 0}
        emptyMessage="No agents on this team yet — add the first peer."
      >
        {(roster) => (
          <ul className="flex flex-col gap-2">
            {roster.map((agent) => (
              <li
                key={agent.id}
                className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 flex items-start justify-between gap-4"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-[13px] font-semibold text-zinc-100 truncate">{agent.name}</p>
                    {agent.memory_enabled ? <StatusPill status="memory" /> : null}
                  </div>
                  {agent.description ? (
                    <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{agent.description}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {capabilitySummary(agent.capabilities).map((cap) => (
                      <span
                        key={cap}
                        className="text-[9px] font-mono uppercase tracking-wider text-emerald-300/80 border border-emerald-500/20 rounded px-1.5 py-0.5"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <GhostButton icon={<Pencil className="w-3.5 h-3.5" />} onClick={() => onEdit(agent)}>
                    Edit
                  </GhostButton>
                  <GhostButton
                    icon={<Trash2 className="w-3.5 h-3.5" />}
                    onClick={() => onDelete(agent)}
                    disabled={remove.isPending}
                    className="hover:text-rose-300 hover:border-rose-500/30"
                  >
                    Delete
                  </GhostButton>
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
    </div>
  );
}
