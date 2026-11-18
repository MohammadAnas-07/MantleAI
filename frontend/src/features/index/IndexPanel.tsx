import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Database, Loader2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { Badge, Banner, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { isActiveRun, keys, useIndexStatus, useRun } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { ApiError, errorMessage } from "../../lib/api/errors";
import { formatCost, formatDateTime, formatTokens } from "../../lib/format";
import type { IndexEstimate, IndexRun } from "../../lib/api/types";
import { FileList } from "./FileList";

const REASON_TEXT: Record<string, string> = {
  embedding_model_changed: "the embedding model changed",
  source_changed: "the source folder changed",
};

/** Index the project: estimate first, then start, watch the run, cancel or delete. */
export function IndexPanel({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const status = useIndexStatus(projectId);
  const [runId, setRunId] = useState<string | null>(null);
  const currentRunId = runId ?? status.data?.active_run_id ?? null;
  const run = useRun(currentRunId);
  const [estimate, setEstimate] = useState<IndexEstimate | null>(null);
  const [costGuard, setCostGuard] = useState<IndexEstimate | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const refreshAll = useCallback(() => {
    void client.invalidateQueries({ queryKey: keys.indexStatus(projectId) });
    void client.invalidateQueries({ queryKey: ["documents", projectId] });
    void client.invalidateQueries({ queryKey: keys.project(projectId) });
    void client.invalidateQueries({ queryKey: keys.projects });
    void client.invalidateQueries({ queryKey: ["usage-records"] });
  }, [client, projectId]);

  const estimateMutation = useMutation({
    mutationFn: () => api.estimate(projectId),
    onSuccess: setEstimate,
  });
  const start = useMutation({
    mutationFn: (force: boolean) => api.startIndex(projectId, force),
    onSuccess: (started) => {
      setRunId(started.run_id);
      setCostGuard(null);
      setEstimate(null);
      refreshAll();
    },
    onError: (error) => {
      // Over the cost limit: show the estimate and ask before forcing.
      if (error instanceof ApiError && error.code === "cost_limit_exceeded") {
        setCostGuard((error.details.estimate as IndexEstimate | undefined) ?? estimate);
      }
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelRun(id),
    onSuccess: (updated) => {
      client.setQueryData(keys.run(updated.id), updated);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteIndex(projectId),
    onSuccess: () => {
      setConfirmDelete(false);
      refreshAll();
    },
  });

  const active = isActiveRun(run.data);
  // When a run reaches an end state, refresh the status and the file list once.
  const endKey = run.data && !active ? `${run.data.id}:${run.data.status}` : null;
  useEffect(() => {
    if (endKey) refreshAll();
  }, [endKey, refreshAll]);

  if (status.isLoading) return <Skeleton label="Loading the index status" />;
  if (status.isError) return <Banner kind="danger">{errorMessage(status.error)}</Banner>;
  const s = status.data;
  if (!s) return null;

  return (
    <div className="space-y-3 text-sm">
      {s.needs_reindex ? (
        <Banner kind="warning">
          Re-index needed: {s.reindex_reasons.map((r) => REASON_TEXT[r] ?? r).join(", ")}. Chat
          won&apos;t use project code until then.
        </Banner>
      ) : null}

      {!s.root_path ? (
        <EmptyState icon={Database}>
          Set a source folder in the project settings to index it.
        </EmptyState>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="label">Folder</dt>
          <dd className="code truncate" title={s.root_path}>
            {s.root_path}
          </dd>
          <dt className="label">Indexed</dt>
          <dd>
            {s.indexed ? `${s.files} files, ${formatDateTime(s.last_indexed_at)}` : "not yet"}
          </dd>
        </dl>
      )}

      {run.data ? (
        <RunCard
          run={run.data}
          onCancel={() => {
            cancel.mutate(run.data.id);
          }}
          cancelling={cancel.isPending}
        />
      ) : null}

      {s.root_path && !active ? (
        <div className="flex flex-wrap gap-2">
          <Button
            busy={estimateMutation.isPending}
            onClick={() => {
              estimateMutation.mutate();
            }}
          >
            Estimate
          </Button>
          {s.indexed ? (
            <Button
              variant="danger"
              icon={<Trash2 aria-hidden className="size-4" />}
              onClick={() => {
                setConfirmDelete(true);
              }}
            >
              Delete index
            </Button>
          ) : null}
        </div>
      ) : null}
      {estimateMutation.isError ? (
        <Banner kind="danger">{errorMessage(estimateMutation.error)}</Banner>
      ) : null}

      {estimate && !active ? (
        <div className="space-y-2 rounded-sm border-2 border-dashed border-line p-2">
          <EstimateTable estimate={estimate} />
          <p className="text-muted">
            Indexing sends the code to {estimate.provider}. Free tiers may use it for training.
          </p>
          <Button
            variant="primary"
            busy={start.isPending}
            onClick={() => {
              start.mutate(false);
            }}
          >
            Start indexing
          </Button>
        </div>
      ) : null}
      {start.isError && !costGuard ? (
        <Banner kind="danger">{errorMessage(start.error)}</Banner>
      ) : null}

      {s.indexed || s.files > 0 ? <FileList projectId={projectId} /> : null}

      <ConfirmDialog
        title="Index above the cost limit?"
        open={costGuard !== null}
        onCancel={() => {
          setCostGuard(null);
        }}
        onConfirm={() => {
          start.mutate(true);
        }}
        confirmLabel="Index anyway"
        busy={start.isPending}
      >
        <p>
          This run is estimated at <strong>{formatCost(costGuard?.cost_usd)}</strong>, above your
          limit of {formatCost(costGuard?.cost_limit_usd)} (INDEX_COST_LIMIT_USD).
        </p>
        {costGuard ? <EstimateTable estimate={costGuard} /> : null}
      </ConfirmDialog>
      <ConfirmDialog
        title="Delete the index?"
        open={confirmDelete}
        danger
        onCancel={() => {
          setConfirmDelete(false);
        }}
        onConfirm={() => {
          remove.mutate();
        }}
        confirmLabel="Delete index"
        busy={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
      >
        <p>All indexed files and their embeddings are removed. Your folder is not touched.</p>
      </ConfirmDialog>
    </div>
  );
}

function EstimateTable({ estimate }: { estimate: IndexEstimate }) {
  const rows: [string, string][] = [
    ["Files to index", String(estimate.files_to_index)],
    ["Unchanged", String(estimate.files_unchanged)],
    ["Skipped", String(estimate.files_skipped)],
    ["Segments to embed", String(estimate.segments_to_embed)],
    ["Tokens", formatTokens(estimate.tokens)],
    ["Cost", formatCost(estimate.cost_usd)],
    ["Provider", `${estimate.provider} (${estimate.model})`],
  ];
  return (
    <table className="w-full text-left">
      <caption className="sr-only">Index estimate</caption>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <th scope="row" className="label pr-2 font-bold">
              {k}
            </th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RunCard({
  run,
  onCancel,
  cancelling,
}: {
  run: IndexRun;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const active = isActiveRun(run);
  const icon = active ? (
    <Loader2 aria-hidden className="size-4 animate-spin" />
  ) : run.status === "succeeded" ? (
    <CircleCheck aria-hidden className="size-4 text-success" />
  ) : (
    <CircleX aria-hidden className="size-4 text-danger" />
  );
  return (
    <div className="space-y-1 rounded-sm border-2 border-dashed border-line p-2" aria-live="polite">
      <div className="flex items-center gap-2">
        {icon}
        <span className="label">Run {run.status}</span>
        {run.error ? <Badge kind="danger">{run.error}</Badge> : null}
        {run.cancel_requested_at && active ? <Badge kind="warning">stopping</Badge> : null}
        {active ? (
          <Button size="sm" className="ml-auto" busy={cancelling} onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
      <p className="text-muted">
        {run.files_indexed} indexed, {run.files_unchanged} unchanged, {run.files_skipped} skipped of{" "}
        {run.files_seen}; {run.chunks_created} segments, {formatTokens(run.tokens)} tokens,{" "}
        {formatCost(run.cost_estimate_usd)}
      </p>
    </div>
  );
}
