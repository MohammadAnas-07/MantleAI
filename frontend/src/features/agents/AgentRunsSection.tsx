import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Feedback";
import { isRunActive, keys, useAgentRun, useAgentRuns } from "../../hooks/queries";
import { useMemoryIndex } from "../../hooks/useMemoryIndex";
import type { AgentRun } from "../../lib/api/types";
import { RunHistory } from "./RunHistory";
import { RunStartForm } from "./RunStartForm";
import { RunView } from "./RunView";
import { useDefaultModel } from "./useDefaultModel";

/**
 * The project's Planner and Reviewer runs. A queued or running run is shown instead of the
 * start form (one at a time per project); a run waiting for approval is shown on open, so it
 * survives a reload or a server restart. `?run=` opens a given run (links from memory).
 */
export function AgentRunsSection({
  projectId,
  defaultModelId,
}: {
  projectId: string;
  defaultModelId: string | null | undefined;
}) {
  const client = useQueryClient();
  const runs = useAgentRuns(projectId);
  const memory = useMemoryIndex(projectId);
  const [params, setParams] = useSearchParams();
  const [startedId, setStartedId] = useState<string | null>(null);
  const [closed, setClosed] = useState(false);
  const fallbackModel = useDefaultModel(defaultModelId);
  const [pickedModel, setPickedModel] = useState<string | null>(null);
  const modelId = pickedModel ?? fallbackModel;
  // The list can be a moment behind a run started here; the run's own poll is not. Same key
  // as RunView's query, so TanStack shares one request.
  const startedRun = useAgentRun(projectId, startedId);

  const refreshList = () => {
    void client.invalidateQueries({ queryKey: keys.agentRuns(projectId) });
  };

  if (runs.isLoading) return <Skeleton label="Loading agent runs" />;
  if (runs.isError) {
    return (
      <QueryError
        error={runs.error}
        onRetry={() => void runs.refetch()}
        retrying={runs.isFetching}
      />
    );
  }
  const items = runs.data?.items ?? [];
  const active = items.find((r) => isRunActive(r));
  const waiting = items.find((r) => r.status === "waiting_for_approval");
  const asked = params.get("run");
  // A run that just ended stays on screen (newest first), so its outcome doesn't vanish.
  const shownId =
    asked ?? startedId ?? active?.id ?? waiting?.id ?? (closed ? null : (items[0]?.id ?? null));
  const blocked = Boolean(active) || isRunActive(startedRun.data);

  const show = (runId: string) => {
    setStartedId(null);
    setClosed(false);
    setParams({ run: runId }, { replace: true });
  };
  const started = (run: AgentRun) => {
    client.setQueryData(keys.agentRun(projectId, run.id), run);
    setParams({}, { replace: true });
    setClosed(false);
    setStartedId(run.id);
    refreshList();
  };

  return (
    <div className="space-y-4">
      {shownId ? (
        <RunView
          key={shownId}
          projectId={projectId}
          runId={shownId}
          memory={memory}
          onPickModel={setPickedModel}
        />
      ) : null}
      {blocked ? (
        <p className="text-sm text-muted">
          A run is in progress. Only one runs at a time per project; the start form comes back when
          it ends.
        </p>
      ) : (
        <section aria-labelledby="start-run" className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id="start-run" className="text-base">
              Start a run
            </h3>
            {shownId ? (
              <Button
                size="sm"
                onClick={() => {
                  setStartedId(null);
                  setClosed(true);
                  setParams({}, { replace: true });
                }}
              >
                Close the shown run
              </Button>
            ) : null}
          </div>
          <RunStartForm
            projectId={projectId}
            modelId={modelId}
            onModelChange={setPickedModel}
            onStarted={started}
            onBusy={refreshList}
          />
        </section>
      )}
      <section aria-labelledby="run-history" className="space-y-2">
        <h3 id="run-history" className="text-base">
          Run history
        </h3>
        <RunHistory runs={items} shownId={shownId} onShow={show} />
      </section>
    </div>
  );
}
