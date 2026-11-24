import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Lock, Trash2, X } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { Badge } from "../../components/ui/Feedback";
import { keys } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { errorMessage, fieldErrors } from "../../lib/api/errors";
import type { MemoryItem, MemoryKind } from "../../lib/api/types";
import { memoryRules } from "../../lib/limits";
import { Dependencies } from "./Dependencies";
import { SupersedeDialog } from "./SupersedeDialog";

export function MemoryItemCard({
  item,
  siblings,
  projectId,
}: {
  item: MemoryItem;
  siblings: MemoryItem[];
  projectId: string;
}) {
  const client = useQueryClient();
  const kind = item.kind as MemoryKind;
  const statusId = useId();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [superseding, setSuperseding] = useState(false);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.memory(projectId, kind) });
    void client.invalidateQueries({ queryKey: keys.memoryItem(item.id) });
    // Stage gates count accepted decisions and tasks.
    void client.invalidateQueries({ queryKey: keys.workflow(projectId) });
  };

  const setStatus = useMutation({
    mutationFn: (status: string) => api.updateMemory(item.id, { status }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api.deleteMemory(item.id),
    onSuccess: () => {
      setConfirmDelete(false);
      refresh();
    },
  });
  const superseded = item.status === "superseded";
  const byTitle = new Map(siblings.map((s) => [s.id, s.title]));

  return (
    <article className="space-y-1 rounded-lg border border-line p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="min-w-0 flex-1 break-words" dir="auto">
          {item.title}
        </h4>
        {item.priority ? <Badge>{item.priority}</Badge> : null}
        {item.source === "agent" ? (
          <Badge kind="info">
            <Bot aria-hidden className="size-3" /> from agent run
          </Badge>
        ) : null}
        {item.is_blocked ? (
          <Badge kind="warning">
            <Lock aria-hidden className="size-3" /> blocked
          </Badge>
        ) : null}
      </div>
      {item.body ? (
        <p className="whitespace-pre-wrap break-words text-muted" dir="auto">
          {item.body}
        </p>
      ) : null}
      {item.why ? (
        <p className="break-words" dir="auto">
          <span className="font-medium">Why: </span>
          {item.why}
        </p>
      ) : null}
      {item.source_agent_run_id ? (
        <p className="text-xs">
          <Link to={`/projects/${projectId}/workflow?run=${item.source_agent_run_id}`}>
            Open the agent run
          </Link>
          {item.stage_key ? <span className="text-muted"> (stage {item.stage_key})</span> : null}
        </p>
      ) : null}
      {kind === "decision" && item.status === "proposed" ? (
        <div role="group" aria-label="Decide on this proposal" className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="primary"
            busy={setStatus.isPending && setStatus.variables === "accepted"}
            disabled={setStatus.isPending}
            aria-label={`Accept ${item.title}`}
            icon={<Check aria-hidden className="size-4" />}
            onClick={() => {
              setStatus.mutate("accepted");
            }}
          >
            Accept
          </Button>
          <Button
            size="sm"
            busy={setStatus.isPending && setStatus.variables === "rejected"}
            disabled={setStatus.isPending}
            aria-label={`Reject ${item.title}`}
            icon={<X aria-hidden className="size-4" />}
            onClick={() => {
              setStatus.mutate("rejected");
            }}
          >
            Reject
          </Button>
        </div>
      ) : null}
      {item.superseded_by_id ? (
        <p className="text-muted">
          Superseded by: {byTitle.get(item.superseded_by_id) ?? "a newer decision"}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={statusId} className="text-xs">
          Status
        </label>
        {superseded ? (
          <Badge>superseded</Badge>
        ) : (
          <select
            id={statusId}
            value={item.status}
            disabled={setStatus.isPending}
            onChange={(e) => {
              setStatus.mutate(e.target.value);
            }}
            className="rounded-sm border border-field bg-paper px-1 text-sm"
          >
            {memoryRules[kind].statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        {kind === "decision" && !superseded ? (
          <Button
            size="sm"
            onClick={() => {
              setSuperseding(true);
            }}
          >
            Supersede
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Delete ${item.title}`}
          className="ml-auto"
          onClick={() => {
            setConfirmDelete(true);
          }}
          icon={<Trash2 aria-hidden className="size-4" />}
        />
      </div>
      {setStatus.isError ? (
        <p role="alert" className="text-danger">
          {fieldErrors(setStatus.error).status ?? errorMessage(setStatus.error)}
        </p>
      ) : null}

      {kind === "task" ? <Dependencies item={item} siblings={siblings} onChange={refresh} /> : null}

      <ConfirmDialog
        title="Delete this item?"
        open={confirmDelete}
        danger
        onCancel={() => {
          setConfirmDelete(false);
        }}
        onConfirm={() => {
          remove.mutate();
        }}
        confirmLabel="Delete"
        busy={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
      >
        <p dir="auto">&ldquo;{item.title}&rdquo; is removed from the project memory.</p>
      </ConfirmDialog>
      {superseding ? (
        <SupersedeDialog
          item={item}
          siblings={siblings}
          onClose={() => {
            setSuperseding(false);
          }}
          onDone={refresh}
        />
      ) : null}
    </article>
  );
}
