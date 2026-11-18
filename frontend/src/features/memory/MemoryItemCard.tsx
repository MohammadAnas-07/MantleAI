import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Lock, Trash2, X } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { FormError, TextArea, TextInput } from "../../components/ui/Field";
import { Badge } from "../../components/ui/Feedback";
import { keys } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { errorMessage, fieldErrors } from "../../lib/api/errors";
import type { MemoryItem, MemoryKind } from "../../lib/api/types";
import { limits, memoryRules, validateMemory } from "../../lib/limits";

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
    <article className="space-y-1 rounded-sm border-2 border-dashed border-line p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="min-w-0 flex-1 break-words" dir="auto">
          {item.title}
        </h4>
        {item.priority ? <Badge>{item.priority}</Badge> : null}
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
          <span className="label">Why: </span>
          {item.why}
        </p>
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
            className="rounded-sm border-2 border-line bg-surface px-1 text-sm"
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

function Dependencies({
  item,
  siblings,
  onChange,
}: {
  item: MemoryItem;
  siblings: MemoryItem[];
  onChange: () => void;
}) {
  const selectId = useId();
  const errorId = useId();
  const [pick, setPick] = useState("");
  const add = useMutation({
    mutationFn: (dependsOn: string) => api.addDependency(item.id, dependsOn),
    onSuccess: () => {
      setPick("");
      onChange();
    },
  });
  const removeDep = useMutation({
    mutationFn: (dependsOn: string) => api.removeDependency(item.id, dependsOn),
    onSuccess: onChange,
  });
  const deps = item.depends_on_ids ?? [];
  const titles = new Map(siblings.map((s) => [s.id, s.title]));
  const candidates = siblings.filter((s) => s.id !== item.id && !deps.includes(s.id));

  return (
    <div className="space-y-1">
      {deps.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {deps.map((dep) => (
            <li key={dep}>
              <Badge>
                needs: {titles.get(dep) ?? "another task"}
                <button
                  type="button"
                  aria-label={`Remove dependency on ${titles.get(dep) ?? "task"}`}
                  onClick={() => {
                    removeDep.mutate(dep);
                  }}
                >
                  <X aria-hidden className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex items-center gap-2">
        <label htmlFor={selectId} className="text-xs">
          Depends on
        </label>
        <select
          id={selectId}
          value={pick}
          aria-invalid={add.isError}
          aria-describedby={add.isError ? errorId : undefined}
          onChange={(e) => {
            setPick(e.target.value);
          }}
          className="min-w-0 flex-1 rounded-sm border-2 border-line bg-surface px-1 text-sm"
        >
          <option value="">Choose a task</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          disabled={!pick}
          busy={add.isPending}
          onClick={() => {
            add.mutate(pick);
          }}
        >
          Add
        </Button>
      </div>
      {add.isError ? (
        // Cycles, self-dependencies and missing tasks come back from the backend; show them here.
        <p id={errorId} role="alert" className="text-danger">
          {errorMessage(add.error)}
        </p>
      ) : null}
      {removeDep.isError ? <p className="text-danger">{errorMessage(removeDep.error)}</p> : null}
    </div>
  );
}

function SupersedeDialog({
  item,
  siblings,
  onClose,
  onDone,
}: {
  item: MemoryItem;
  siblings: MemoryItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const selectId = useId();
  const [byId, setById] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [why, setWhy] = useState("");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const run = useMutation({
    mutationFn: () =>
      api.supersede(
        item.id,
        byId
          ? { by_id: byId }
          : {
              decision: {
                title: title.trim(),
                ...(body.trim() ? { body: body.trim() } : {}),
                ...(why.trim() ? { why: why.trim() } : {}),
              },
            },
      ),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  const others = siblings.filter((s) => s.id !== item.id && s.status !== "superseded");
  const errors = { ...fieldErrors(run.error), ...clientErrors };

  const submit = () => {
    if (!byId) {
      const found = validateMemory({ title, body, why });
      setClientErrors(found);
      if (Object.keys(found).length > 0) return;
    }
    run.mutate();
  };

  return (
    <Dialog title="Supersede decision" open onClose={onClose}>
      <div className="space-y-3 text-sm">
        <p dir="auto">&ldquo;{item.title}&rdquo; will be marked superseded.</p>
        <div className="flex flex-col gap-1">
          <label htmlFor={selectId}>Replace with an existing decision</label>
          <select
            id={selectId}
            value={byId}
            onChange={(e) => {
              setById(e.target.value);
            }}
            className="rounded-sm border-2 border-line bg-surface px-2 py-1.5"
          >
            <option value="">No: write a new decision below</option>
            {others.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
              </option>
            ))}
          </select>
        </div>
        {!byId ? (
          <>
            <TextInput
              label="New decision"
              value={title}
              maxLength={limits.memoryTitle}
              onChange={(e) => {
                setTitle(e.target.value);
              }}
              error={errors.title}
              dir="auto"
            />
            <TextArea
              label="What was decided"
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
              }}
              error={errors.body}
            />
            <TextArea
              label="Why"
              value={why}
              onChange={(e) => {
                setWhy(e.target.value);
              }}
              error={errors.why}
            />
          </>
        ) : null}
        <FormError message={run.isError && !errors.title ? errorMessage(run.error) : null} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={run.isPending} onClick={submit}>
            Supersede
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
