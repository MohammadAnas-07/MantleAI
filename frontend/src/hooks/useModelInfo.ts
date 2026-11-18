import { useMemo } from "react";

import type { Model } from "../lib/api/types";
import { useModels, useProviders } from "./queries";

export interface ModelInfo {
  byId: Map<string, Model>;
  chatModels: Model[];
  embeddingModels: Model[];
  hasKey: (model: Model | undefined) => boolean;
  name: (id: string | null | undefined) => string;
}

/** Models with a lookup by id and "does the user have a key for its provider". */
export function useModelInfo(): ModelInfo & { isLoading: boolean } {
  const models = useModels();
  const providers = useProviders();
  return useMemo(() => {
    const list = models.data ?? [];
    const withKey = new Set((providers.data ?? []).filter((p) => p.has_key).map((p) => p.id));
    const byId = new Map(list.map((m) => [m.id, m]));
    return {
      isLoading: models.isLoading || providers.isLoading,
      byId,
      chatModels: list.filter((m) => m.kind === "chat" && m.enabled),
      embeddingModels: list.filter((m) => m.kind === "embedding" && m.enabled),
      hasKey: (model) => Boolean(model && withKey.has(model.provider)),
      name: (id) => (id ? (byId.get(id)?.display_name ?? "Unknown model") : "None"),
    };
  }, [models.data, models.isLoading, providers.data, providers.isLoading]);
}
