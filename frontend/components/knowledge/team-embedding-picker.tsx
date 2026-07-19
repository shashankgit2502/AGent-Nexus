"use client";

/**
 * Runtime embedding-model selector for a team (ITEM 2, ARCH §9.5).
 *
 * Knowledge can only be embedded once the team (or org default) has an embedding
 * model, so this is surfaced right where sources are added. Lists only
 * `model_type='embedding'` catalog models and PUTs the choice to the team. The
 * pgvector collection is keyed by the chosen model, so switching it changes the
 * embedding space for *future* ingestions (existing chunks keep their model).
 */
import { Field, SelectInput } from "@/components/crud/primitives";
import { useCatalog } from "@/features/providers/use-providers";
import { useTeam, useSetTeamEmbeddingModel } from "@/features/knowledge/use-knowledge";

export function TeamEmbeddingPicker({ teamId }: { teamId: string }) {
  const team = useTeam(teamId);
  const catalog = useCatalog();
  const setModel = useSetTeamEmbeddingModel();

  const embeddingModels = (catalog.data ?? []).filter((m) => m.model_type === "embedding");
  const current = team.data?.embedding_model_id ?? "";

  return (
    <div className="mt-3">
      <Field
        label="Embedding model"
        hint="Used to ingest + search this team's knowledge (falls back to org default)"
      >
        <SelectInput
          value={current}
          disabled={team.isLoading || setModel.isPending}
          onChange={(e) =>
            setModel.mutate({ teamId, embeddingModelId: e.target.value || null })
          }
        >
          <option value="">Org default</option>
          {embeddingModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name}
            </option>
          ))}
        </SelectInput>
      </Field>
      {embeddingModels.length === 0 ? (
        <p className="text-[10px] text-amber-400/80 font-mono mt-1">
          No embedding models in the catalog. In Settings → AI → Catalog, add a model with
          type <span className="text-amber-300">embedding</span> (or set an existing
          model&apos;s type to embedding) to enable ingestion.
        </p>
      ) : null}
      {setModel.isError ? (
        <p className="text-[10px] text-rose-400 font-mono mt-1">{setModel.error.message}</p>
      ) : null}
    </div>
  );
}
