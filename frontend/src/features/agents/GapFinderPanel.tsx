import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { Banner, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { keys, useGapRuns } from "../../hooks/queries";
import { useMemoryIndex, type MemoryIndex } from "../../hooks/useMemoryIndex";
import { useModelInfo } from "../../hooks/useModelInfo";
import { api } from "../../lib/api/endpoints";
import { ApiError } from "../../lib/api/errors";
import { formatCost, formatDateTime } from "../../lib/format";
import type { AgentRun, GapFinding, GapReport, RunEstimate, RunWarning } from "../../lib/api/types";
import { RunStatusBadge, SeverityBadge } from "./RunBadges";
import { failureText, startErrorText } from "./runText";
import { CostGuardDialog, ModelSelect, References, Warnings } from "./shared";
import { useDefaultModel } from "./useDefaultModel";

const GROUPS: { key: keyof GapReport; title: string }[] = [
  { key: "missing_steps", title: "Missing steps" },
  { key: "risks", title: "Risks" },
  { key: "technical_debt", title: "Technical debt" },
  { key: "scalability_concerns", title: "Scalability concerns" },
];

/** Runs the gap finder on request (one model call) and lists its results. */
export function GapFinderPanel({
  projectId,
  defaultModelId,
}: {
  projectId: string;
  defaultModelId: string | null | undefined;
}) {
  const client = useQueryClient();
  const runs = useGapRuns(projectId);
  const memory = useMemoryIndex(projectId);
  const models = useModelInfo();
  const fallback = useDefaultModel(defaultModelId);
  const [picked, setPicked] = useState<string | null>(null);
  const modelId = picked ?? fallback;
  const [shownId, setShownId] = useState<string | null>(null);
  const [costGuard, setCostGuard] = useState<RunEstimate | null>(null);

  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.gapRuns(projectId) });
    void client.invalidateQueries({ queryKey: ["usage-records"] });
  };
  const run = useMutation({
    mutationFn: (force: boolean) => api.runGapFinder(projectId, { model_id: modelId, force }),
    onSuccess: (done) => {
      setCostGuard(null);
      setShownId(done.id);
      refresh();
    },
    onError: (error) => {
      if (!(error instanceof ApiError)) return;
      if (error.code === "cost_limit_exceeded") {
        setCostGuard((error.details.estimate as RunEstimate | undefined) ?? null);
        return;
      }
      setCostGuard(null);
      // A failed call is saved as a failed run: show it from the list.
      if (typeof error.details.run_id === "string") {
        setShownId(error.details.run_id);
        refresh();
      }
    },
  });

  const items = runs.data?.items ?? [];
  const shown = items.find((r) => r.id === shownId) ?? items[0];
  const model = models.byId.get(modelId);

  return (
    <div className="space-y-3">
      <p className="text-base">
        The gap finder reads the project memory and the current stage and lists missing steps,
        risks, technical debt and scalability concerns. It changes nothing.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-60">
          <ModelSelect label="Gap finder model" value={modelId} onChange={setPicked} />
        </div>
        <Button
          variant="primary"
          busy={run.isPending}
          disabled={!modelId}
          icon={<Search aria-hidden className="size-4" />}
          onClick={() => {
            run.mutate(false);
          }}
        >
          Find gaps
        </Button>
      </div>
      <p className="text-sm text-muted">
        One model call{model ? ` to ${model.display_name}` : ""} with your API key (one retry if the
        answer is invalid). Your provider bills you for it.
      </p>
      <div aria-live="polite">
        {run.isPending ? <p className="text-base">Finding gaps… this can take a minute.</p> : null}
        {run.isError && !costGuard ? (
          <Banner kind="danger">{startErrorText(run.error)}</Banner>
        ) : null}
      </div>

      {runs.isLoading ? <Skeleton label="Loading gap finder results" /> : null}
      {runs.isError ? (
        <QueryError
          error={runs.error}
          onRetry={() => void runs.refetch()}
          retrying={runs.isFetching}
        />
      ) : null}
      {runs.data && items.length === 0 ? (
        <EmptyState icon={Search}>No gap finder results yet.</EmptyState>
      ) : null}
      {shown ? <GapResult run={shown} projectId={projectId} memory={memory} /> : null}

      {items.length > 1 ? (
        <div>
          <h4 className="text-base font-medium">Past results</h4>
          <ul className="space-y-1 text-base">
            {items.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  aria-pressed={r.id === shown?.id}
                  onClick={() => {
                    setShownId(r.id);
                  }}
                >
                  {formatDateTime(r.created_at)}
                </Button>
                <RunStatusBadge status={r.status} />
                <span>{models.name(r.model_id)}</span>
                <span>{formatCost(r.cost_usd)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <CostGuardDialog
        estimate={costGuard}
        busy={run.isPending}
        onCancel={() => {
          setCostGuard(null);
        }}
        onForce={() => {
          run.mutate(true);
        }}
      />
    </div>
  );
}

function GapResult({
  run,
  projectId,
  memory,
}: {
  run: AgentRun;
  projectId: string;
  memory: MemoryIndex;
}) {
  if (run.status === "failed") {
    return (
      <Banner kind="danger">
        Gap finder run from {formatDateTime(run.created_at)} failed:{" "}
        {failureText(run.error ?? "", run.error_message)}
      </Banner>
    );
  }
  const report = run.result as Partial<GapReport>;
  const total = GROUPS.reduce((n, g) => n + (report[g.key]?.length ?? 0), 0);
  return (
    <article aria-label="Gap finder result" className="space-y-3 rounded-lg border border-line p-4">
      <p className="text-base text-muted">
        {formatDateTime(run.created_at)}, stage {run.stage_id ?? "?"}, {total} findings,{" "}
        {formatCost(run.cost_usd)}
      </p>
      <Warnings warnings={run.warnings as RunWarning[]} />
      {GROUPS.map((group) => (
        <FindingGroup
          key={group.key}
          title={group.title}
          findings={report[group.key] ?? []}
          projectId={projectId}
          memory={memory}
        />
      ))}
    </article>
  );
}

function FindingGroup({
  title,
  findings,
  projectId,
  memory,
}: {
  title: string;
  findings: GapFinding[];
  projectId: string;
  memory: MemoryIndex;
}) {
  return (
    <section aria-label={title} className="space-y-1">
      <h4 className="text-base font-medium">
        {title} ({findings.length})
      </h4>
      {findings.length === 0 ? <p className="text-base text-muted">None found.</p> : null}
      <ul className="space-y-2">
        {findings.map((f, i) => (
          <li key={i} className="space-y-0.5 text-base">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium break-words" dir="auto">
                {f.title}
              </span>
              <SeverityBadge severity={f.severity} />
            </div>
            <p className="whitespace-pre-wrap break-words" dir="auto">
              {f.explanation}
            </p>
            <References refs={f.refers_to} projectId={projectId} memory={memory} />
          </li>
        ))}
      </ul>
    </section>
  );
}
