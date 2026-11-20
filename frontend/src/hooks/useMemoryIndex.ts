import { useMemo } from "react";

import type { MemoryItem } from "../lib/api/types";
import { useMemory } from "./queries";

export interface MemoryIndex {
  get: (id: string) => MemoryItem | undefined;
  isLoading: boolean;
}

/** Every requirement, decision and task of the project by id, to show references by title.
 * Uses the same queries as the memory panel, so it shares their cache. */
export function useMemoryIndex(projectId: string): MemoryIndex {
  const requirements = useMemory(projectId, "requirement");
  const decisions = useMemory(projectId, "decision");
  const tasks = useMemory(projectId, "task");
  return useMemo(() => {
    const byId = new Map<string, MemoryItem>();
    for (const page of [requirements.data, decisions.data, tasks.data]) {
      for (const item of page?.items ?? []) byId.set(item.id, item);
    }
    return {
      get: (id) => byId.get(id),
      isLoading: requirements.isLoading || decisions.isLoading || tasks.isLoading,
    };
  }, [
    requirements.data,
    decisions.data,
    tasks.data,
    requirements.isLoading,
    decisions.isLoading,
    tasks.isLoading,
  ]);
}
