// Selection and edits of a plan being approved, as plain data and pure functions. The state
// lives in the approval view and is only replaced by the user's own actions, so a failed
// approve, a refetch or a re-render never loses it.

import { ApiError } from "../../lib/api/errors";
import type { ApproveRunBody, Plan, ProposedDecision, ProposedTask } from "../../lib/api/types";

export type Kind = "task" | "decision";
export type TaskFields = Pick<ProposedTask, "title" | "description" | "priority">;
export type DecisionFields = Pick<ProposedDecision, "title" | "what" | "why" | "alternatives">;

export interface ApprovalState {
  tasks: boolean[];
  decisions: boolean[];
  taskEdits: Record<number, Partial<TaskFields>>;
  decisionEdits: Record<number, Partial<DecisionFields>>;
}

export type ApprovalAction =
  | { type: "toggle"; kind: Kind; index: number }
  | { type: "selectAll"; selected: boolean }
  | { type: "editTask"; index: number; field: keyof TaskFields; value: string }
  | { type: "editDecision"; index: number; field: keyof DecisionFields; value: string }
  | { type: "undoEdit"; kind: Kind; index: number };

/** Everything starts selected: the user takes out what they don't want. */
export function initialState(plan: Plan): ApprovalState {
  return {
    tasks: plan.tasks.map(() => true),
    decisions: plan.decisions.map(() => true),
    taskEdits: {},
    decisionEdits: {},
  };
}

export function reducer(state: ApprovalState, action: ApprovalAction): ApprovalState {
  switch (action.type) {
    case "toggle": {
      const key = action.kind === "task" ? "tasks" : "decisions";
      return { ...state, [key]: state[key].map((v, i) => (i === action.index ? !v : v)) };
    }
    case "selectAll":
      return {
        ...state,
        tasks: state.tasks.map(() => action.selected),
        decisions: state.decisions.map(() => action.selected),
      };
    case "editTask":
      return {
        ...state,
        taskEdits: {
          ...state.taskEdits,
          [action.index]: { ...state.taskEdits[action.index], [action.field]: action.value },
        },
      };
    case "editDecision":
      return {
        ...state,
        decisionEdits: {
          ...state.decisionEdits,
          [action.index]: { ...state.decisionEdits[action.index], [action.field]: action.value },
        },
      };
    case "undoEdit": {
      const key = action.kind === "task" ? "taskEdits" : "decisionEdits";
      const rest = Object.fromEntries(
        Object.entries(state[key]).filter(([index]) => Number(index) !== action.index),
      );
      return { ...state, [key]: rest };
    }
  }
}

/** Only fields that differ from the proposal, as the user typed them (trimmed). */
function changes<T extends Record<string, string>>(
  proposed: T,
  edits: Partial<T> | undefined,
): Partial<T> {
  const out: Partial<T> = {};
  for (const [field, value] of Object.entries(edits ?? {}) as [keyof T, string][]) {
    const trimmed = value.trim();
    if (trimmed !== proposed[field]) out[field] = trimmed as T[keyof T];
  }
  return out;
}

export function selectedCount(state: ApprovalState): number {
  return [...state.tasks, ...state.decisions].filter(Boolean).length;
}

/** The request body: `all` when everything is chosen unchanged, else the chosen indexes with
 * their edits. */
export function approveBody(plan: Plan, state: ApprovalState): ApproveRunBody {
  const tasks = plan.tasks.flatMap((task, index) =>
    state.tasks[index] ? [{ index, ...changes<TaskFields>(task, state.taskEdits[index]) }] : [],
  );
  const decisions = plan.decisions.flatMap((decision, index) =>
    state.decisions[index]
      ? [{ index, ...changes<DecisionFields>(decision, state.decisionEdits[index]) }]
      : [],
  );
  const everything =
    tasks.length === plan.tasks.length && decisions.length === plan.decisions.length;
  const edited = [...tasks, ...decisions].some((item) => Object.keys(item).length > 1);
  return everything && !edited
    ? { all: true, tasks: [], decisions: [] }
    : { all: false, tasks, decisions };
}

export interface DanglingDependency {
  task: number;
  dependsOn: number;
}

/** Chosen tasks that depend on a task the user left out: that link won't be saved. */
export function danglingDependencies(plan: Plan, state: ApprovalState): DanglingDependency[] {
  return plan.tasks.flatMap((task, index) =>
    state.tasks[index]
      ? task.depends_on
          .filter((dep) => !state.tasks[dep])
          .map((dep) => ({ task: index, dependsOn: dep }))
      : [],
  );
}

export interface ItemErrors {
  message?: string;
  fields: Record<string, string>;
}

export interface ApproveErrors {
  form: string | null;
  items: Record<string, ItemErrors>; // "task:3", "decision:0"
}

// The projects module names the stored fields; the form shows the proposal's names.
const FIELD: Record<Kind, Record<string, string>> = {
  task: { body: "description" },
  decision: { body: "what" },
};

/**
 * Where the backend's answer to an approve belongs: a field of an item (invalid_draft), an
 * item (draft_limits_changed), a request-body field (validation_error, indexed by position in
 * what was sent), or the whole form.
 */
export function approveErrors(error: unknown, sent: ApproveRunBody | null): ApproveErrors {
  const out: ApproveErrors = { form: null, items: {} };
  if (!(error instanceof ApiError)) {
    out.form = error ? "Something went wrong." : null;
    return out;
  }
  const add = (key: string, field: string | null, message: string) => {
    const item = (out.items[key] ??= { fields: {} });
    if (field) item.fields[field] = message;
    else item.message = message;
  };
  const { details } = error;
  const kind = details.kind === "task" || details.kind === "decision" ? details.kind : null;
  const index = typeof details.index === "number" ? details.index : null;

  if (error.code === "invalid_draft" && kind && index !== null && Array.isArray(details.errors)) {
    for (const e of details.errors as { field?: unknown; message?: unknown }[]) {
      const field = typeof e.field === "string" ? e.field : "";
      const message = typeof e.message === "string" ? e.message : error.message;
      add(`${kind}:${index}`, FIELD[kind][field] ?? field, message);
    }
    out.form = "Fix the marked item, or leave it out, then approve again.";
    return out;
  }
  if (error.code === "draft_limits_changed" && kind && index !== null) {
    add(`${kind}:${index}`, null, error.message);
    out.form = "The limits changed since this plan was made. Fix the marked item or leave it out.";
    return out;
  }
  if (error.code === "validation_error" && Array.isArray(details.errors)) {
    for (const e of details.errors as { loc?: unknown; msg?: unknown }[]) {
      const loc: unknown[] = Array.isArray(e.loc) ? (e.loc as unknown[]) : [];
      const [, list, position, field] = loc;
      const sentList =
        list === "tasks" ? sent?.tasks : list === "decisions" ? sent?.decisions : undefined;
      const planIndex = typeof position === "number" ? sentList?.[position]?.index : undefined;
      if (planIndex !== undefined && typeof field === "string" && typeof e.msg === "string") {
        add(`${list === "tasks" ? "task" : "decision"}:${planIndex}`, field, e.msg);
      }
    }
    out.form = Object.keys(out.items).length
      ? "Fix the marked fields, then approve again."
      : error.message;
    return out;
  }
  out.form = error.message;
  return out;
}
