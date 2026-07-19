"use client";

/**
 * Memory Explorer (ARCH §14/§10/§25.1, FRONTEND_SPEC §14).
 *
 * Team→agent drill-down (memory is per-agent-namespaced in the backend), then the
 * agent's structured records grouped into the §14 sections — Facts (semantic),
 * Experiences (episodic), Session Learnings, Summaries — with **search**, **pin**,
 * and **delete**. The team-shared layer is shown read-only (agents may not pollute
 * it, §25.1). Records are the `GET /agents/{id}/memories` list; the shared blob is
 * the rendered recall view (`GET /agents/{id}/memory`). All data logic lives in the
 * `features/memory` hooks; this screen is presentational.
 */
import { useState } from "react";
import { HardDrive, Pin, PinOff, Search, Trash2 } from "lucide-react";
import {
  CrudPage,
  EmptyState,
  GhostButton,
  Pane,
  QueryBoundary,
  SectionTitle,
  TextInput,
} from "@/components/crud/primitives";
import { TeamPicker, AgentPicker } from "@/components/crud/resource-pickers";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  useAgentMemories,
  useAgentRecall,
  useDeleteMemory,
  usePinMemory,
} from "@/features/memory/use-memory";
import { groupByKind } from "@/features/memory/memory-model";
import type { MemoryItemRead } from "@/types/api";

export default function MemoryPage() {
  const [teamId, setTeamId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 250);

  // limit=200: per-agent memory is small; sections group the page client-side.
  const memories = useAgentMemories(agentId || null, { q: q || undefined, limit: 200 });
  const recall = useAgentRecall(agentId || null);

  return (
    <CrudPage
      eyebrow="Long-term memory"
      title="Memory Explorer"
      description="Browse an agent's long-term memory — facts, experiences, and learnings it keeps across sessions — plus the read-only team-shared layer."
    >
      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-5">
        <Pane>
          <div className="flex flex-col gap-3">
            <TeamPicker
              value={teamId}
              onChange={(id) => {
                setTeamId(id);
                setAgentId("");
              }}
            />
            <AgentPicker teamId={teamId || null} value={agentId} onChange={setAgentId} />
            <label className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
              <TextInput
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search memories…"
                className="pl-9"
                disabled={!agentId}
                aria-label="Search memories"
              />
            </label>
          </div>
        </Pane>

        <Pane>
          {agentId ? (
            <div className="flex flex-col gap-6">
              <QueryBoundary
                isLoading={memories.isLoading}
                error={memories.error}
                data={memories.data}
                emptyMessage="No records to show."
              >
                {(page) => (
                  <PrivateRecords agentId={agentId} items={page.items} searching={Boolean(q)} />
                )}
              </QueryBoundary>
              <SharedLayer body={recall.data?.shared ?? null} />
            </div>
          ) : (
            <EmptyState
              message="Pick a team and agent to explore its memory."
              icon={<HardDrive className="w-7 h-7" />}
            />
          )}
        </Pane>
      </div>
    </CrudPage>
  );
}

function PrivateRecords({
  agentId,
  items,
  searching,
}: {
  agentId: string;
  items: MemoryItemRead[];
  searching: boolean;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        message={searching ? "No memories match your search." : "This agent has no memories yet."}
        icon={<HardDrive className="w-7 h-7" />}
      />
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {groupByKind(items).map(({ kind, label, hint, items: inKind }) => (
        <section key={kind}>
          <SectionTitle label={`${label} (${inKind.length})`} hint={hint} />
          <div className="flex flex-col gap-2">
            {inKind.map((item) => (
              <MemoryCard key={item.id} agentId={agentId} item={item} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function MemoryCard({ agentId, item }: { agentId: string; item: MemoryItemRead }) {
  const pin = usePinMemory();
  const remove = useDeleteMemory();
  const busy = pin.isPending || remove.isPending;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12.5px] text-zinc-200 leading-relaxed whitespace-pre-wrap">
          {item.content}
        </p>
        <div className="flex shrink-0 items-center gap-1.5">
          <GhostButton
            icon={item.pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
            title={item.pinned ? "Unpin" : "Pin"}
            aria-label={item.pinned ? "Unpin memory" : "Pin memory"}
            disabled={busy}
            className={item.pinned ? "text-emerald-300 border-emerald-500/30" : ""}
            onClick={() => pin.mutate({ agentId, itemId: item.id, pinned: !item.pinned })}
          />
          <GhostButton
            icon={<Trash2 className="w-3.5 h-3.5" />}
            title="Delete"
            aria-label="Delete memory"
            disabled={busy}
            className="text-rose-300 hover:text-rose-200 border-rose-500/20"
            onClick={() => remove.mutate({ agentId, itemId: item.id })}
          />
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-zinc-600">
        {item.pinned ? <span className="text-emerald-400/80">Pinned</span> : null}
        <span>{new Date(item.created_at).toLocaleString()}</span>
      </div>
    </div>
  );
}

function SharedLayer({ body }: { body: string | null }) {
  return (
    <section>
      <SectionTitle label="Team-shared" hint="Shared policies/notes — read-only (§25.1)" />
      {body ? (
        <pre className="text-[12px] text-zinc-300 whitespace-pre-wrap font-mono bg-black/30 border border-white/10 rounded-xl p-4 leading-relaxed">
          {body}
        </pre>
      ) : (
        <p className="text-[11px] text-zinc-600 italic">No team-shared memory.</p>
      )}
    </section>
  );
}
