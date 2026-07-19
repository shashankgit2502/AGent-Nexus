"use client";

/**
 * Master-detail DETAIL (ITEM 1, ARCH §14). The models belonging to ONE connection,
 * lazily fetched (only when the parent row is expanded), searchable by identifier/
 * display name, and paginated server-side. Replaces the old single flat catalog
 * scroll: each connection owns its own searchable model list.
 */
import { useEffect, useState } from "react";
import { Search, Trash2 } from "lucide-react";
import { TextInput, QueryBoundary, GhostButton, SelectInput } from "@/components/crud/primitives";
import {
  useConnectionModels,
  useDeleteCatalogModel,
  useUpdateCatalogModel,
} from "@/features/providers/use-providers";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import type { CatalogModelRead, ModelType, UUID } from "@/types/api";

const PAGE_SIZE = 25;

export function ConnectionModelsList({
  connectionId,
  active,
}: {
  connectionId: UUID;
  active: boolean;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const debounced = useDebouncedValue(search.trim());

  // A new search resets to the first page (stale offset could skip past all matches).
  useEffect(() => setOffset(0), [debounced]);

  const models = useConnectionModels(
    connectionId,
    { q: debounced || undefined, limit: PAGE_SIZE, offset },
    active,
  );

  const total = models.data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="flex flex-col gap-3 pt-3">
      <div className="relative">
        <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
        <TextInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search models by name or identifier…"
          className="pl-9"
        />
      </div>

      <QueryBoundary
        isLoading={models.isLoading}
        error={models.error}
        data={models.data?.items}
        isEmpty={(d) => d.length === 0}
        emptyMessage={
          debounced ? "No models match this search." : "No models yet — discover or add one."
        }
      >
        {(list) => (
          <ul className="flex flex-col gap-2">
            {list.map((m) => (
              <ModelRow key={m.id} model={m} />
            ))}
          </ul>
        )}
      </QueryBoundary>

      {total > PAGE_SIZE ? (
        <div className="flex items-center justify-between text-[10.5px] text-zinc-500 font-mono">
          <span>
            {from}–{to} of {total}
          </span>
          <div className="flex items-center gap-2">
            <GhostButton onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} disabled={offset === 0}>
              Prev
            </GhostButton>
            <GhostButton onClick={() => setOffset((o) => o + PAGE_SIZE)} disabled={to >= total}>
              Next
            </GhostButton>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** One model row with two inline controls, both PATCHing the catalog row:
 * - **tools** — toggle the §9.3 `supports_tools` gate (chat models only). Discovery
 *   can't read tool-capability for OpenAI-compatible endpoints (NVIDIA NIM, vLLM, …)
 *   and defaults it to `false`, so this is how a genuinely tool-capable model is made
 *   mesh-eligible without a DB edit (Approach B, ARCH §9.3).
 * - **type** — reclassify chat↔embedding so a mislabeled model shows in the team
 *   embedding picker, without delete + re-add (Approach B, ARCH §9.5). */
function ModelRow({ model }: { model: CatalogModelRead }) {
  const update = useUpdateCatalogModel();
  const remove = useDeleteCatalogModel();
  const busy = update.isPending || remove.isPending;

  return (
    <li className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-2.5 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold text-zinc-100 truncate">{model.display_name}</p>
        <p className="text-[10px] text-zinc-500 font-mono truncate">{model.model_identifier}</p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {model.model_type === "chat" ? (
          <button
            type="button"
            aria-label="Toggle tool-calling (supports_tools)"
            aria-pressed={model.supports_tools}
            disabled={busy}
            title={
              model.supports_tools
                ? "Tool-capable — mesh-eligible (§9.3). Click to disable."
                : "Not tool-capable — agents can't use this model in the mesh. Click to enable if the model supports function-calling."
            }
            onClick={() =>
              update.mutate({ id: model.id, payload: { supports_tools: !model.supports_tools } })
            }
            className={
              "text-[9px] font-mono uppercase tracking-wider rounded px-1.5 py-0.5 transition-colors disabled:opacity-40 " +
              (model.supports_tools
                ? "text-emerald-300/80 border border-emerald-500/30 hover:border-emerald-400/50"
                : "text-zinc-500 border border-white/10 hover:text-emerald-300/70 hover:border-emerald-500/20")
            }
          >
            tools
          </button>
        ) : null}
        <SelectInput
          value={model.model_type}
          disabled={busy}
          title="Model type — set to embedding to use it for knowledge ingestion"
          aria-label="Model type"
          className="w-32 py-1 text-[10px]"
          onChange={(e) =>
            update.mutate({ id: model.id, payload: { model_type: e.target.value as ModelType } })
          }
        >
          <option value="chat">chat</option>
          <option value="embedding">embedding</option>
        </SelectInput>
        <button
          type="button"
          title="Delete model"
          onClick={() => {
            if (window.confirm(`Delete model "${model.display_name}"?`)) remove.mutate(model.id);
          }}
          disabled={busy}
          className="p-1.5 rounded-lg border border-white/10 bg-white/[0.02] text-zinc-400 hover:text-rose-400 hover:border-rose-500/30 transition-colors disabled:opacity-40"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </li>
  );
}
