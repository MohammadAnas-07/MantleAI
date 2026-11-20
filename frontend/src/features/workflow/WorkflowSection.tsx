import { useState } from "react";

import { QueryError } from "../../components/QueryError";
import { ReasonDialog } from "../../components/ReasonDialog";
import { Button } from "../../components/ui/Button";
import { Banner, Skeleton } from "../../components/ui/Feedback";
import { useWorkflow } from "../../hooks/queries";
import { ApiError } from "../../lib/api/errors";
import type { Workflow } from "../../lib/api/types";
import { EventHistory } from "./EventHistory";
import { StageBar } from "./StageBar";
import { StagePanel, UnmetList } from "./StagePanel";
import { useWorkflowActions, type WorkflowActions } from "./useWorkflowActions";

/** The stage bar, the stage the user looks at, and the history. */
export function WorkflowSection({ projectId }: { projectId: string }) {
  const workflow = useWorkflow(projectId);
  const actions = useWorkflowActions(projectId);

  if (workflow.isLoading) return <Skeleton label="Loading the workflow" />;
  if (workflow.error instanceof ApiError && workflow.error.code === "unknown_stage") {
    return <UnknownStage message={workflow.error.message} actions={actions} />;
  }
  if (workflow.isError) {
    return (
      <QueryError
        error={workflow.error}
        onRetry={() => void workflow.refetch()}
        retrying={workflow.isFetching}
      />
    );
  }
  if (!workflow.data) return null;
  return <WorkflowView workflow={workflow.data} actions={actions} />;
}

function WorkflowView({ workflow, actions }: { workflow: Workflow; actions: WorkflowActions }) {
  const current = workflow.current_stage_id;
  const [picked, setPicked] = useState<string | null>(null);
  // Follow the current stage unless the user opened another one that still exists.
  const viewing =
    workflow.stages.find((s) => s.id === picked)?.id ?? current ?? workflow.stages.at(-1)?.id ?? "";
  const stage = workflow.stages.find((s) => s.id === viewing);
  const currentIndex = current
    ? workflow.stages.findIndex((s) => s.id === current)
    : workflow.stages.length;
  const viewingIndex = workflow.stages.findIndex((s) => s.id === viewing);

  return (
    <div className="space-y-4">
      {/* Status changes are announced: the user may have acted in another tab. */}
      <div aria-live="polite" className="space-y-2">
        {actions.notice ? (
          <Banner
            kind="warning"
            action={
              <Button size="sm" onClick={actions.clearNotice}>
                Dismiss
              </Button>
            }
          >
            {actions.notice.text}
            {actions.notice.unmet ? <UnmetList unmet={actions.notice.unmet} /> : null}
          </Banner>
        ) : null}
        {workflow.status === "completed" ? (
          <Banner kind="success">
            Every stage is approved or skipped. Reopen a stage to change it.
          </Banner>
        ) : null}
      </div>
      <StageBar stages={workflow.stages} viewing={viewing} onView={setPicked} />
      {stage ? (
        <StagePanel
          key={stage.id}
          stage={stage}
          canReopen={viewingIndex >= 0 && viewingIndex < currentIndex}
          actions={actions}
        />
      ) : null}
      <section aria-labelledby="workflow-history" className="space-y-2">
        <h3 id="workflow-history" className="text-base">
          History
        </h3>
        <EventHistory
          events={workflow.events}
          total={workflow.events_total}
          stages={workflow.stages}
        />
      </section>
    </div>
  );
}

/** The stored stage was removed from stages.yaml: the only way on is a reset. */
function UnknownStage({ message, actions }: { message: string; actions: WorkflowActions }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <Banner
        kind="warning"
        action={
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setOpen(true);
            }}
          >
            Reset workflow…
          </Button>
        }
      >
        {message}
      </Banner>
      {open ? (
        <ReasonDialog
          title="Reset the workflow?"
          open
          danger
          confirmLabel="Reset"
          busy={actions.reset.isPending}
          error={actions.reset.error}
          onCancel={() => {
            setOpen(false);
            actions.reset.reset();
          }}
          onSubmit={(reason) => {
            actions.reset.mutate(reason, {
              onSuccess: () => {
                setOpen(false);
              },
            });
          }}
        >
          <p>
            The workflow goes back to the first stage and every stage status is cleared. Checklist
            ticks of stages that still exist are kept. Project memory is not touched.
          </p>
        </ReasonDialog>
      ) : null}
    </div>
  );
}
