import { useModelInfo } from "../../hooks/useModelInfo";

/** The project's default model if it can be used, else the first chat model with a key. */
export function useDefaultModel(defaultModelId: string | null | undefined): string {
  const models = useModelInfo();
  if (defaultModelId && models.byId.has(defaultModelId)) return defaultModelId;
  return models.chatModels.find((m) => models.hasKey(m))?.id ?? "";
}
