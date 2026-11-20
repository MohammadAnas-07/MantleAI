import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { keys } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { ApiError } from "../../lib/api/errors";
import type { Unmet, Workflow } from "../../lib/api/types";

/** Answers that mean "what you see is out of date": the page reloads the workflow. */
const STALE: Record<string, string> = {
  workflow_changed:
    "The workflow was changed somewhere else (another tab or request). This page now shows the latest state. Check it and try again.",
  workflow_completed: "The workflow is already completed. Reopen a stage to change it.",
  not_an_earlier_stage:
    "That stage is no longer before the current one. The page now shows the latest state.",
  stage_gate_unmet: "The stage can't be approved yet. The page now shows what is missing.",
};

export interface Notice {
  text: string;
  unmet?: Unmet[];
}

/**
 * Every workflow change. A success replaces the cached workflow with the answer; a 409 that
 * means the page is stale reloads it and leaves a notice that says why.
 */
export function useWorkflowActions(projectId: string) {
  const client = useQueryClient();
  const [notice, setNotice] = useState<Notice | null>(null);

  const onSuccess = (workflow: Workflow) => {
    setNotice(null);
    client.setQueryData(keys.workflow(projectId), workflow);
  };
  const onError = (error: unknown) => {
    if (!(error instanceof ApiError) || error.status !== 409) return;
    const text = STALE[error.code];
    if (!text) return;
    const unmet = Array.isArray(error.details.unmet) ? (error.details.unmet as Unmet[]) : undefined;
    setNotice({ text, ...(unmet ? { unmet } : {}) });
    void client.invalidateQueries({ queryKey: keys.workflow(projectId) });
  };
  const options = { onSuccess, onError };

  return {
    notice,
    clearNotice: () => {
      setNotice(null);
    },
    checklist: useMutation({
      mutationFn: (body: { stage_id: string; item_id: string; done: boolean }) =>
        api.setChecklistItem(projectId, body),
      ...options,
    }),
    approve: useMutation({
      mutationFn: (body: { stage_id: string; force?: boolean; reason?: string }) =>
        api.approveStage(projectId, body),
      ...options,
    }),
    skip: useMutation({
      mutationFn: (body: { stage_id: string; reason: string }) => api.skipStage(projectId, body),
      ...options,
    }),
    reopen: useMutation({
      mutationFn: (body: { stage_id: string; reason: string }) => api.reopenStage(projectId, body),
      ...options,
    }),
    reset: useMutation({
      mutationFn: (reason: string) => api.resetWorkflow(projectId, reason),
      ...options,
    }),
  };
}

export type WorkflowActions = ReturnType<typeof useWorkflowActions>;

/** True when the error is one the notice already explains (no second message needed). */
export function isStaleError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code in STALE;
}
