/**
 * Slice-4 unit test: the pure Model-Resolution form logic (Connection / Catalog /
 * Profile). Node env — exercises numeric parsing edge cases (blank → null,
 * out-of-range → null), the supports_tools gate for embeddings, base-URL
 * requirement per provider, and the form→DTO mappings.
 */
import { describe, it, expect } from "vitest";
import {
  providerNeedsBaseUrl,
  validateConnection,
  toConnectionCreate,
  connectionFormFromRead,
  toConnectionUpdate,
  initialConnectionForm,
  parseOptionalInt,
  parseOptionalFloat,
  validateCatalog,
  toCatalogCreate,
  initialCatalogForm,
  validateProfile,
  toProfileCreate,
  initialProfileForm,
  parseInUseAgentNames,
} from "@/features/providers/provider-model";

describe("connection", () => {
  it("requires a base URL for self-hosted/azure providers only", () => {
    expect(providerNeedsBaseUrl("openai")).toBe(false);
    expect(providerNeedsBaseUrl("azure_openai")).toBe(true);
    expect(providerNeedsBaseUrl("ollama")).toBe(true);
  });

  it("validates name and base-url requirement", () => {
    expect(validateConnection({ ...initialConnectionForm(), displayName: "" })).toMatch(/name/i);
    expect(
      validateConnection({ ...initialConnectionForm(), displayName: "x", provider: "ollama", baseUrl: "" }),
    ).toMatch(/base url/i);
    expect(
      validateConnection({ ...initialConnectionForm(), displayName: "x", provider: "openai" }),
    ).toBeNull();
  });

  it("maps blank optional fields to null", () => {
    const dto = toConnectionCreate({ ...initialConnectionForm(), displayName: "OpenAI Prod" });
    expect(dto.display_name).toBe("OpenAI Prod");
    expect(dto.base_url).toBeNull();
    expect(dto.api_key_ref).toBeNull();
  });

  it("prefills the edit form from a connection without exposing the key", () => {
    const form = connectionFormFromRead({
      id: "c1",
      org_id: "o1",
      display_name: "OpenRouter",
      provider: "openrouter",
      base_url: "https://openrouter.ai/api/v1",
      api_version: null,
      scope: "org",
      team_id: null,
      enabled: true,
      validated_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });
    expect(form.displayName).toBe("OpenRouter");
    expect(form.provider).toBe("openrouter");
    expect(form.baseUrl).toBe("https://openrouter.ai/api/v1");
    expect(form.apiKeyRef).toBe(""); // write-only — never returned
  });

  it("omits a blank key on update so the stored credential is preserved", () => {
    const base = { ...initialConnectionForm(), displayName: "Conn", provider: "openai" as const };
    expect("api_key_ref" in toConnectionUpdate(base)).toBe(false);
    expect(toConnectionUpdate({ ...base, apiKeyRef: "sk-new" }).api_key_ref).toBe("sk-new");
  });
});

describe("numeric parsing", () => {
  it("parseOptionalInt: blank → null, valid int → number, invalid → null", () => {
    expect(parseOptionalInt("")).toBeNull();
    expect(parseOptionalInt("128000")).toBe(128000);
    expect(parseOptionalInt("-1")).toBeNull();
    expect(parseOptionalInt("1.5")).toBeNull();
    expect(parseOptionalInt("abc")).toBeNull();
  });

  it("parseOptionalFloat: respects range bounds", () => {
    expect(parseOptionalFloat("", 0, 2)).toBeNull();
    expect(parseOptionalFloat("0.7", 0, 2)).toBe(0.7);
    expect(parseOptionalFloat("2.5", 0, 2)).toBeNull();
    expect(parseOptionalFloat("1.0", 0, 1)).toBe(1);
  });
});

describe("catalog", () => {
  it("requires connection, name, and identifier", () => {
    expect(validateCatalog({ ...initialCatalogForm() })).toMatch(/connection/i);
    expect(
      validateCatalog({ ...initialCatalogForm(), providerConnectionId: "c1", displayName: "" }),
    ).toMatch(/display name/i);
  });

  it("never claims tool support for embedding models", () => {
    const dto = toCatalogCreate({
      ...initialCatalogForm(),
      providerConnectionId: "c1",
      displayName: "Embed",
      modelIdentifier: "text-embedding-3",
      modelType: "embedding",
      supportsTools: true, // user toggled, but embeddings can't call tools
    });
    expect(dto.supports_tools).toBe(false);
    expect(dto.source).toBe("manual");
  });

  it("rejects a non-integer context window", () => {
    expect(
      validateCatalog({
        ...initialCatalogForm(),
        providerConnectionId: "c1",
        displayName: "x",
        modelIdentifier: "y",
        contextWindow: "12.5",
      }),
    ).toMatch(/context window/i);
  });
});

describe("profile", () => {
  it("validates name and param ranges", () => {
    expect(validateProfile({ ...initialProfileForm(), name: "" })).toMatch(/name/i);
    expect(validateProfile({ ...initialProfileForm(), name: "p", temperature: "5" })).toMatch(/temperature/i);
    expect(validateProfile({ ...initialProfileForm(), name: "p", topP: "2" })).toMatch(/top_p/i);
    expect(validateProfile({ ...initialProfileForm(), name: "p" })).toBeNull();
  });

  it("maps blank params to null and keeps booleans", () => {
    const dto = toProfileCreate({ ...initialProfileForm(), name: "Balanced", temperature: "0.7" });
    expect(dto.name).toBe("Balanced");
    expect(dto.temperature).toBe(0.7);
    expect(dto.top_p).toBeNull();
    expect(dto.max_tokens).toBeNull();
    expect(dto.default_model_id).toBeNull();
    expect(dto.streaming).toBe(true);
  });
});

describe("parseInUseAgentNames (profile-delete 409)", () => {
  it("extracts agent names from a well-formed 409 detail", () => {
    const detail = {
      message: "profile is in use by agents; reassign them before deleting",
      agents: [
        { id: "a1", name: "Researcher" },
        { id: "a2", name: "Planner" },
      ],
    };
    expect(parseInUseAgentNames(detail)).toEqual(["Researcher", "Planner"]);
  });

  it("returns null for unrelated/malformed shapes (defensive)", () => {
    expect(parseInUseAgentNames("connection not found")).toBeNull();
    expect(parseInUseAgentNames(null)).toBeNull();
    expect(parseInUseAgentNames({ message: "no agents key" })).toBeNull();
  });

  it("skips entries missing a name rather than throwing", () => {
    const detail = { agents: [{ id: "a1" }, { id: "a2", name: "Planner" }] };
    expect(parseInUseAgentNames(detail)).toEqual(["Planner"]);
  });
});
