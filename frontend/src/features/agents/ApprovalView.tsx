import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useReducer, useState } from "react";

import { ReasonDialog } from "../../components/ReasonDialog";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Dialog";
import { Banner } from "../../components/ui/Feedback";
import { keys } from "../../hooks/queries";
import type { MemoryIndex } from "../../hooks/useMemoryIndex";
import { api } from "../../lib/api/endpoints";
import { ApiError } from "../../lib/api/errors";
import type { AgentRun, ApproveRunBody, ApproveRunResult, Plan, Review } from "../../lib/api/types";
import {
  approveBody,
  approveErrors,
  danglingDependencies,
  initialState,
  reducer,
  selectedCount,
  type DecisionFields,
  type TaskFields,
} from "./approvalState";
import { DecisionItem, TaskItem } from "./PlanItems";
import { ReviewPanel } from "./ReviewPanel";

/** 409s on approve and reject: another tab or request decided first. */
const RACED = new Set(["agent_run_not_waiting"]);

/**
 * The Planner's draft next to the Reviewer's verdict. The user picks items, edits them and
 * approves or rejects; only that writes project memory.
 */
export function ApprovalView({
  run,
  projectId,
  memory,
  onApproved,
  onRaced,
}: {
  run: AgentRun;
  projectId: string;
  memory: MemoryIndex;
  onApproved: (result: ApproveRunResult) => void;
  onRaced: (message: string) => void;
}) {
  const client = useQueryClient();
  const plan = run.result.plan as Plan;
  const review = run.result.review as Review | undefined;
  const [state, dispatch] = useReducer(reducer, plan, initialState);
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [sent, setSent] = useState<ApproveRunBody | null>(null);

  const refreshRun = () => {
    void client.invalidateQueries({ queryKey: keys.agentRun(projectId, run.id) });
    void client.invalidateQueries({ queryKey: keys.agentRuns(projectId) });
  };
  const raced = (error: unknown) => {
    if (error instanceof ApiError && error.status === 409 && RACED.has(error.code)) {
      onRaced(
        "This run was already approved or rejected somewhere else (another tab?). Nothing was saved here. It now shows its current state.",
      );
      refreshRun();
      return true;
    }
    return false;
  };

  const approve = useMutation({
    mutationFn: (body: ApproveRunBody) => api.approveAgentRun(run.id, body),
    onSuccess: (result) => {
      setConfirming(false);
      client.setQueryData(keys.agentRun(projectId, run.id), result.run);
      void client.invalidateQueries({ queryKey: ["memory", projectId] });
      void client.invalidateQueries({ queryKey: keys.workflow(projectId) });
      void client.invalidateQueries({ queryKey: keys.agentRuns(projectId) });
      onApproved(result);
    },
    onError: (error) => {
      setConfirming(false);
      raced(error);
    },
  });
  const reject = useMutation({
    mutationFn: (reason: string) => api.rejectAgentRun(run.id, reason),
    onSuccess: (updated) => {
      setRejecting(false);
      client.setQueryData(keys.agentRun(projectId, run.id), updated);
      void client.invalidateQueries({ queryKey: keys.agentRuns(projectId) });
    },
    onError: (error) => {
      if (raced(error)) setRejecting(false);
    },
  });

  const errors = approveErrors(approve.error, sent);
  const dangling = danglingDependencies(plan, state);
  const chosen = selectedCount(state);
  const total = plan.tasks.length + plan.decisions.length;
  const taskTitle = (i: number) =>
    state.taskEdits[i]?.title?.trim() || plan.tasks[i]?.title || `task ${i + 1}`;
  const planTitle = (ref: string) => {
    const [kind, n] = ref.split(":");
    const i = Number(n);
    return kind === "task" ? taskTitle(i) : plan.decisions[i]?.title;
  };
  const chosenTasks = state.tasks.filter(Boolean).length;
  const chosenDecisions = state.decisions.filter(Boolean).length;

  return (
    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
      <section aria-labelledby="plan-title" className="space-y-3">
        <h3 id="plan-title" className="text-base">
          Planner draft
        </h3>
        <div role="group" aria-label="Selection" className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() => {
              dispatch({ type: "selectAll", selected: true });
            }}
          >
            Select all
          </Button>
          <Button
            size="sm"
            onClick={() => {
              dispatch({ type: "selectAll", selected: false });
            }}
          >
            Select none
          </Button>
          <span className="text-sm" aria-live="polite">
            {chosen} of {total} selected
          </span>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-base font-medium">Proposed tasks ({plan.tasks.length})</legend>
          <ul className="space-y-2">
            {plan.tasks.map((task, i) => (
              <TaskItem
                key={i}
                index={i}
                task={task}
                value={{ ...pickTask(task), ...state.taskEdits[i] }}
                selected={state.tasks[i] ?? false}
                errors={errors.items[`task:${i}`]}
                titleOf={taskTitle}
                projectId={projectId}
                memory={memory}
                onToggle={() => {
                  dispatch({ type: "toggle", kind: "task", index: i });
                }}
                onChange={(field, value) => {
                  dispatch({ type: "editTask", index: i, field, value });
                }}
                onUndo={() => {
                  dispatch({ type: "undoEdit", kind: "task", index: i });
                }}
              />
            ))}
          </ul>
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="text-base font-medium">
            Proposed decisions ({plan.decisions.length})
          </legend>
          <p className="text-xs text-muted">
            Decisions are saved as proposed; you accept them later in memory.
          </p>
          <ul className="space-y-2">
            {plan.decisions.map((decision, i) => (
              <DecisionItem
                key={i}
                index={i}
                decision={decision}
                value={{ ...pickDecision(decision), ...state.decisionEdits[i] }}
                selected={state.decisions[i] ?? false}
                errors={errors.items[`decision:${i}`]}
                onToggle={() => {
                  dispatch({ type: "toggle", kind: "decision", index: i });
                }}
                onChange={(field, value) => {
                  dispatch({ type: "editDecision", index: i, field, value });
                }}
                onUndo={() => {
                  dispatch({ type: "undoEdit", kind: "decision", index: i });
                }}
              />
            ))}
          </ul>
        </fieldset>
        <PlanNotes plan={plan} />

        <div aria-live="polite" className="space-y-2">
          {dangling.length > 0 ? (
            <Banner kind="warning">
              <p>
                Some chosen tasks depend on tasks you left out. Those links won&apos;t be saved:
              </p>
              <ul className="list-disc pl-5">
                {dangling.map((d) => (
                  <li key={`${d.task}-${d.dependsOn}`} dir="auto">
                    &ldquo;{taskTitle(d.task)}&rdquo; depends on &ldquo;{taskTitle(d.dependsOn)}
                    &rdquo;
                  </li>
                ))}
              </ul>
            </Banner>
          ) : null}
          {errors.form && !(approve.error instanceof ApiError && RACED.has(approve.error.code)) ? (
            <Banner kind="danger">{errors.form}</Banner>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            disabled={chosen === 0}
            busy={approve.isPending}
            onClick={() => {
              setConfirming(true);
            }}
          >
            Approve selected…
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              setRejecting(true);
            }}
          >
            Reject run…
          </Button>
          {chosen === 0 ? (
            <span className="text-sm text-muted">Select at least one item, or reject the run.</span>
          ) : null}
        </div>
      </section>

      {review ? (
        <ReviewPanel review={review} projectId={projectId} memory={memory} planTitle={planTitle} />
      ) : null}

      <ConfirmDialog
        title="Save the selected items?"
        open={confirming}
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
          const body = approveBody(plan, state);
          setSent(body);
          approve.mutate(body);
        }}
        confirmLabel="Approve and save"
        busy={approve.isPending}
      >
        <p>
          {chosenTasks} tasks (as todo) and {chosenDecisions} decisions (as proposed) are added to
          the project memory.
        </p>
        {dangling.length > 0 ? (
          <p>
            {dangling.length} dependency link{dangling.length === 1 ? "" : "s"} to tasks you left
            out will not be saved.
          </p>
        ) : null}
      </ConfirmDialog>
      {rejecting ? (
        <ReasonDialog
          title="Reject this run?"
          open
          danger
          confirmLabel="Reject"
          busy={reject.isPending}
          error={reject.error}
          onCancel={() => {
            setRejecting(false);
            reject.reset();
          }}
          onSubmit={(reason) => {
            reject.mutate(reason);
          }}
        >
          <p>Nothing from this run is saved. The reason is kept with the run.</p>
        </ReasonDialog>
      ) : null}
    </div>
  );
}

const pickTask = ({ title, description, priority }: TaskFields): TaskFields => ({
  title,
  description,
  priority,
});
const pickDecision = ({ title, what, why, alternatives }: DecisionFields): DecisionFields => ({
  title,
  what,
  why,
  alternatives,
});

function PlanNotes({ plan }: { plan: Plan }) {
  const groups: [string, string[]][] = [
    ["Assumptions", plan.assumptions],
    ["Risks", plan.risks],
    ["Open questions", plan.open_questions],
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {groups.map(([title, items]) => (
        <section key={title} aria-label={title} className="text-sm">
          <h4 className="text-base font-medium">{title}</h4>
          {items.length === 0 ? <p className="text-muted">None.</p> : null}
          <ul className="list-disc pl-5">
            {items.map((text, i) => (
              <li key={i} className="break-words" dir="auto">
                {text}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
