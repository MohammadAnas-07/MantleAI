import { CircleAlert, CircleCheck, Square, SquareCheck } from "lucide-react";
import { useState } from "react";

import { ReasonDialog } from "../../components/ReasonDialog";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Feedback";
import { FormError } from "../../components/ui/Field";
import { errorMessage } from "../../lib/api/errors";
import type { Stage, Unmet } from "../../lib/api/types";
import { isStaleError, type WorkflowActions } from "./useWorkflowActions";

type Dialog = "skip" | "force" | "reopen" | null;

/**
 * One stage: its goal, checklist, gate and actions. Approve and skip exist only on the
 * current stage and always send its id; reopen exists only on an earlier stage.
 */
export function StagePanel({
  stage,
  canReopen,
  actions,
}: {
  stage: Stage;
  canReopen: boolean;
  actions: WorkflowActions;
}) {
  const [dialog, setDialog] = useState<Dialog>(null);
  const isCurrent = stage.status === "current";
  const { checklist, approve, skip, reopen } = actions;
  const close = () => {
    setDialog(null);
    approve.reset();
    skip.reset();
    reopen.reset();
  };
  // A stale page closes the dialog: the notice above the stages explains what changed.
  const done = {
    onSuccess: () => {
      setDialog(null);
    },
    onError: (error: unknown) => {
      if (isStaleError(error)) setDialog(null);
    },
  };
  const pendingItem = checklist.isPending ? checklist.variables.item_id : null;
  const approveError = approve.isError && !isStaleError(approve.error) && dialog === null;

  return (
    <section aria-labelledby={`stage-${stage.id}`} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={`stage-${stage.id}`} className="text-base">
          {stage.title}
        </h3>
        <Badge kind={isCurrent ? "warning" : "neutral"}>{stage.status}</Badge>
      </div>
      <p>
        <span className="label">Goal: </span>
        {stage.goal}
      </p>

      <fieldset className="space-y-1">
        <legend className="label text-sm">Checklist</legend>
        <ul className="space-y-1">
          {stage.checklist.map((item) => (
            <li key={item.id} className="flex items-start gap-2 text-sm">
              <input
                id={`check-${stage.id}-${item.id}`}
                type="checkbox"
                className="mt-1 size-4 accent-[var(--accent)]"
                checked={item.done}
                disabled={pendingItem === item.id}
                onChange={(e) => {
                  checklist.mutate({
                    stage_id: stage.id,
                    item_id: item.id,
                    done: e.target.checked,
                  });
                }}
              />
              <label htmlFor={`check-${stage.id}-${item.id}`}>
                {item.text}{" "}
                <span className="text-xs text-muted">
                  ({item.required ? "required" : "optional"})
                </span>
              </label>
            </li>
          ))}
        </ul>
        {checklist.isError && !isStaleError(checklist.error) ? (
          <FormError message={errorMessage(checklist.error)} />
        ) : null}
      </fieldset>

      {stage.artifacts.length > 0 ? (
        <div className="text-sm">
          <h4 className="label text-sm">Project memory needed</h4>
          <ul>
            {stage.artifacts.map((a) => (
              <li key={a.text} className="flex items-center gap-1">
                {a.met ? (
                  <SquareCheck aria-hidden className="size-4 text-success" />
                ) : (
                  <Square aria-hidden className="size-4" />
                )}
                {a.text} ({a.have} of {a.need}, {a.met ? "met" : "not met"})
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <GateStatus stage={stage} />

      <div className="flex flex-wrap gap-2">
        {isCurrent && stage.ready ? (
          <Button
            variant="primary"
            busy={approve.isPending && dialog === null}
            onClick={() => {
              approve.mutate({ stage_id: stage.id });
            }}
          >
            Approve stage
          </Button>
        ) : null}
        {isCurrent && !stage.ready ? (
          <Button
            onClick={() => {
              setDialog("force");
            }}
          >
            Approve anyway…
          </Button>
        ) : null}
        {isCurrent ? (
          <Button
            onClick={() => {
              setDialog("skip");
            }}
          >
            Skip stage…
          </Button>
        ) : null}
        {canReopen ? (
          <Button
            onClick={() => {
              setDialog("reopen");
            }}
          >
            Reopen this stage…
          </Button>
        ) : null}
      </div>
      {approveError ? <FormError message={errorMessage(approve.error)} /> : null}

      {dialog === "force" ? (
        <ReasonDialog
          title={`Approve "${stage.title}" without its gate?`}
          open
          onCancel={close}
          confirmLabel="Approve anyway"
          danger
          busy={approve.isPending}
          error={!isStaleError(approve.error) ? approve.error : null}
          onSubmit={(reason) => {
            approve.mutate({ stage_id: stage.id, force: true, reason }, done);
          }}
        >
          <p>These are not met yet. The override and your reason are saved in the history.</p>
          <UnmetList unmet={stage.unmet} />
        </ReasonDialog>
      ) : null}
      {dialog === "skip" ? (
        <ReasonDialog
          title={`Skip "${stage.title}"?`}
          open
          onCancel={close}
          confirmLabel="Skip stage"
          busy={skip.isPending}
          error={!isStaleError(skip.error) ? skip.error : null}
          onSubmit={(reason) => {
            skip.mutate({ stage_id: stage.id, reason }, done);
          }}
        >
          <p>The stage is marked skipped without checking its gate.</p>
        </ReasonDialog>
      ) : null}
      {dialog === "reopen" ? (
        <ReasonDialog
          title={`Reopen "${stage.title}"?`}
          open
          onCancel={close}
          confirmLabel="Reopen"
          busy={reopen.isPending}
          error={!isStaleError(reopen.error) ? reopen.error : null}
          onSubmit={(reason) => {
            reopen.mutate({ stage_id: stage.id, reason }, done);
          }}
        >
          <p>This stage and every later one go back to pending. Checklist ticks stay.</p>
        </ReasonDialog>
      ) : null}
    </section>
  );
}

function GateStatus({ stage }: { stage: Stage }) {
  if (stage.ready) {
    return (
      <p className="flex items-center gap-1 text-sm">
        <CircleCheck aria-hidden className="size-4 text-success" />
        <span className="label">Gate met:</span> every required item is done.
      </p>
    );
  }
  return (
    <div className="space-y-1 text-sm">
      <p className="flex items-center gap-1">
        <CircleAlert aria-hidden className="size-4 text-danger" />
        <span className="label">Gate not met:</span> {stage.unmet.length} missing
      </p>
      <UnmetList unmet={stage.unmet} />
    </div>
  );
}

export function UnmetList({ unmet }: { unmet: Unmet[] }) {
  return (
    <ul aria-label="Unmet" className="list-disc pl-5 text-sm">
      {unmet.map((u) => (
        <li key={`${u.type}:${u.id}`}>
          {u.text}
          {u.type === "artifact" && u.have !== null && u.have !== undefined
            ? ` (have ${u.have}, need ${u.need ?? "?"})`
            : ""}
          {u.type === "checklist" ? " (checklist)" : ""}
        </li>
      ))}
    </ul>
  );
}
