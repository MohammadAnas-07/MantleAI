import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { Badge, Banner, Skeleton } from "../../components/ui/Feedback";
import { isRunActive, keys, useAgentRun } from "../../hooks/queries";
import type { MemoryIndex } from "../../hooks/useMemoryIndex";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { ApiError, errorMessage } from "../../lib/api/errors";
import { formatCost, formatDateTime, formatTokens } from "../../lib/format";
import type {
  AgentRun,
  ApproveRunResult,
  Review,
  RunEstimate,
  RunWarning,
} from "../../lib/api/types";
import { MemoryLink } from "../memory/MemoryLink";
import { ApprovalView } from "./ApprovalView";
import { ReviewPanel } from "./ReviewPanel";
import { RunStatusBadge } from "./RunBadges";
import { failureText, RUN_TYPE_LABEL, suggestedModels } from "./runText";
import { SuggestedModels, Warnings } from "./shared";
import { Table } from "../../components/ui/Table";

/** One plan or review run: polled while it runs, then its approval view or its outcome. */
export function RunView({
  projectId,
  runId,
  memory,
  onPickModel,
}: {
  projectId: string;
  runId: string;
  memory: MemoryIndex;
  onPickModel: (modelId: string) => void;
}) {
  const client = useQueryClient();
  const query = useAgentRun(projectId, runId);
  const [notice, setNotice] = useState<string | null>(null);
  const [approved, setApproved] = useState<ApproveRunResult | null>(null);
  // A response for another project (it can't happen with project-scoped keys, but a stale
  // answer must never be shown on the wrong page).
  const run = query.data?.project_id === projectId ? query.data : undefined;

  // When the run leaves queued/running, refresh the list and the activity log once.
  const settled = run && !isRunActive(run) ? `${run.id}:${run.status}` : null;
  useEffect(() => {
    if (!settled) return;
    void client.invalidateQueries({ queryKey: keys.agentRuns(projectId) });
    void client.invalidateQueries({ queryKey: ["usage-records"] });
  }, [settled, client, projectId]);

  const cancel = useMutation({
    mutationFn: () => api.cancelAgentRun(runId),
    onSuccess: (updated) => {
      client.setQueryData(keys.agentRun(projectId, runId), updated);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "agent_run_not_active") {
        // It ended before the cancel arrived: show what really happened.
        setNotice("The run had already ended before the cancel arrived. Its real status is shown.");
        void query.refetch();
      }
    },
  });

  if (query.isLoading) return <Skeleton label="Loading the run" />;
  if (query.isError) {
    return (
      <QueryError
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  if (!run) return null;
  const active = isRunActive(run);

  return (
    <article aria-label="Agent run" className="space-y-3 rounded-lg border border-line p-3">
      <RunHeader run={run} />
      <div aria-live="polite" className="space-y-2">
        <p className="text-sm">
          <span className="font-medium">Status: </span>
          <RunStatusBadge status={run.status} /> {active ? <span>{progressText(run)}</span> : null}
          {run.cancel_requested_at && active ? <Badge kind="warning">stopping</Badge> : null}
        </p>
        {notice ? <Banner kind="info">{notice}</Banner> : null}
        {cancel.isError &&
        !(cancel.error instanceof ApiError && cancel.error.code === "agent_run_not_active") ? (
          <Banner kind="danger">{errorMessage(cancel.error)}</Banner>
        ) : null}
      </div>
      {active ? (
        <Button
          busy={cancel.isPending}
          disabled={Boolean(run.cancel_requested_at)}
          onClick={() => {
            cancel.mutate();
          }}
        >
          Cancel run
        </Button>
      ) : null}

      {run.status === "failed" ? (
        <Banner kind="danger">
          <p>{failureText(run.error ?? "", run.error_message)}</p>
          <SuggestedModels models={suggestedModels(run.error_details)} onPick={onPickModel} />
        </Banner>
      ) : null}
      <Warnings warnings={run.warnings as RunWarning[]} />

      {run.status === "waiting_for_approval" && run.result.plan ? (
        <ApprovalView
          key={run.id}
          run={run}
          projectId={projectId}
          memory={memory}
          onApproved={setApproved}
          onRaced={setNotice}
        />
      ) : null}
      {run.status !== "waiting_for_approval" && run.result.review ? (
        <ReviewPanel review={run.result.review as Review} projectId={projectId} memory={memory} />
      ) : null}
      {run.status === "approved" ? (
        <Saved run={run} result={approved} projectId={projectId} memory={memory} />
      ) : null}
      {run.status === "rejected" ? (
        <p className="text-sm break-words" dir="auto">
          <span className="font-medium">Rejected: </span>
          {run.decision_reason}
        </p>
      ) : null}
      <StepTable run={run} />
    </article>
  );
}

function progressText(run: AgentRun): string {
  if (run.status === "queued") return "Waiting to start.";
  const done = run.steps.filter((s) => s.status === "succeeded").length;
  if (run.run_type === "plan")
    return done === 0 ? "The Planner is drafting." : "The Reviewer is checking the draft.";
  return "The Reviewer is checking the project memory.";
}

function RunHeader({ run }: { run: AgentRun }) {
  const models = useModelInfo();
  const estimate = run.estimate as Partial<RunEstimate>;
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
      <h3 className="text-base">{RUN_TYPE_LABEL[run.run_type] ?? run.run_type}</h3>
      <span>{models.name(run.model_id)}</span>
      <time dateTime={run.created_at} className="text-muted">
        {formatDateTime(run.created_at)}
      </time>
      <span>
        Estimate {formatCost(estimate.cost_usd ?? null)}, used {formatCost(run.cost_usd)} (
        {formatTokens(run.input_tokens)} in / {formatTokens(run.output_tokens)} out)
      </span>
      {run.stage_id ? <span className="text-muted">stage {run.stage_id}</span> : null}
    </div>
  );
}

/** What an approval created, with links; works after a reload too (saved_item_ids). */
function Saved({
  run,
  result,
  projectId,
  memory,
}: {
  run: AgentRun;
  result: ApproveRunResult | null;
  projectId: string;
  memory: MemoryIndex;
}) {
  return (
    <div className="space-y-1 text-sm">
      <Banner kind="success">
        Saved {run.saved_item_ids.length} items to the project memory. Tasks are todo; decisions are
        proposed until you accept them.
      </Banner>
      <ul aria-label="Created items" className="list-disc pl-5">
        {run.saved_item_ids.map((id) => (
          <li key={id}>
            <MemoryLink projectId={projectId} id={id} index={memory} />
          </li>
        ))}
      </ul>
      {result ? <Warnings warnings={result.warnings as RunWarning[]} /> : null}
    </div>
  );
}

function StepTable({ run }: { run: AgentRun }) {
  if (run.steps.length === 0) return null;
  return (
    <Table caption="Steps" showCaption>
      <thead>
        <tr>
          <th scope="col">Agent</th>
          <th scope="col">Status</th>
          <th scope="col" className="num">
            Attempts
          </th>
          <th scope="col" className="num">
            Tokens in/out
          </th>
          <th scope="col" className="num">
            Cost
          </th>
          <th scope="col" className="num">
            Time
          </th>
        </tr>
      </thead>
      <tbody>
        {run.steps.map((s) => (
          <tr key={s.position}>
            <td>{s.agent}</td>
            <td>
              {s.status}
              {s.error ? ` (${s.error})` : ""}
            </td>
            <td className="num">{s.attempts}</td>
            <td className="num">
              {formatTokens(s.input_tokens)}/{formatTokens(s.output_tokens)}
            </td>
            <td className="num">{formatCost(s.cost_usd)}</td>
            <td className="num">{(s.latency_ms / 1000).toFixed(1)} s</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
