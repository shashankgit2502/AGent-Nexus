"use client";

/**
 * Settings → AI (Slice 4, ARCH §9/§27).
 *
 * The 3-layer Model Resolution stack — Connection → Catalog → Inference Profile —
 * replacing the reference's flat `InferenceProfile`. Each layer is an independent
 * React Query panel (list + create). Ordered top-down so the dependency reads
 * naturally: you register a connection, add models to it, then bundle a profile.
 */
import { CrudPage } from "@/components/crud/primitives";
import { ConnectionsPanel } from "@/components/providers/connections-panel";
import { CatalogPanel } from "@/components/providers/catalog-panel";
import { ProfilesPanel } from "@/components/providers/profiles-panel";

export default function AiSettingsPage() {
  return (
    <CrudPage
      eyebrow="Slice 4 · CRUD"
      title="AI Settings"
      description="Configure the Model Resolution layer: provider connections, the model catalog (with the supports_tools gate), and the inference profiles agents reference."
    >
      <div className="flex flex-col gap-5 max-w-4xl">
        <ConnectionsPanel />
        <CatalogPanel />
        <ProfilesPanel />
      </div>
    </CrudPage>
  );
}
