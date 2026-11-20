// Workflow and agent run answers for component tests. Shapes follow the generated schema.

import type {
  AgentRun,
  MemoryItem,
  Plan,
  Review,
  Stage,
  Workflow,
  WorkflowEvent,
} from "../lib/api/types";
import { MODEL_SMALL, PROJECT_ID } from "./fixtures";

export const PROJECT_B = "22222222-2222-4222-8222-222222222222";
export const RUN_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
export const REQ_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
export const TASK_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
export const DECISION_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";

const STAGE_IDS = [
  ["requirements", "Requirements"],
  ["architecture", "Architecture"],
  ["technical_decisions", "Technical decisions"],
  ["task_breakdown", "Task breakdown"],
  ["implementation_plan", "Implementation plan"],
] as const;

export function stage(id: string, title: string, status: string, ready = false): Stage {
  const checklist = [
    { id: "goal", text: `Goal of ${title} is written down.`, required: true, done: ready },
    { id: "scope", text: `Scope of ${title} is written down.`, required: true, done: ready },
    { id: "extra", text: `Extras of ${title} are listed.`, required: false, done: false },
  ];
  const unmet = ready
    ? []
    : [
        { type: "checklist", id: "goal", text: checklist[0]?.text ?? "", have: null, need: null },
        { type: "artifact", id: "0", text: "At least 1 approved requirement.", have: 0, need: 1 },
      ];
  return {
    id,
    title,
    goal: `The goal of ${title}.`,
    status,
    checklist,
    artifacts: [
      {
        text: "At least 1 approved requirement.",
        kind: "requirement",
        statuses: ["approved"],
        have: ready ? 1 : 0,
        need: 1,
        met: ready,
      },
    ],
    unmet,
    ready,
  };
}

/** A workflow at stage `currentIndex` (5 = completed); earlier stages are approved. */
export function workflow(
  currentIndex = 0,
  { ready = false, events = [] as WorkflowEvent[], version = 1 } = {},
): Workflow {
  const stages = STAGE_IDS.map(([id, title], i) =>
    stage(
      id,
      title,
      i < currentIndex ? "approved" : i === currentIndex ? "current" : "pending",
      i < currentIndex || ready,
    ),
  );
  return {
    project_id: PROJECT_ID,
    status: currentIndex >= STAGE_IDS.length ? "completed" : "active",
    current_stage_id: STAGE_IDS[currentIndex]?.[0] ?? null,
    version,
    stages,
    events,
    events_total: events.length,
  };
}

export function event(action: string, extra: Partial<WorkflowEvent> = {}): WorkflowEvent {
  return {
    id: `ev-${action}-${Math.random().toString(16).slice(2)}`,
    action,
    stage_id: "requirements",
    item_id: null,
    actor: "user",
    reason: null,
    forced: false,
    details: {},
    created_at: "2026-11-20T10:00:00Z",
    ...extra,
  };
}

export const memoryItem = (
  id: string,
  kind: string,
  title: string,
  extra: Partial<MemoryItem> = {},
): MemoryItem => ({
  id,
  project_id: PROJECT_ID,
  kind,
  title,
  body: "",
  status: kind === "decision" ? "accepted" : kind === "task" ? "todo" : "approved",
  priority: null,
  why: null,
  alternatives: null,
  decided_at: null,
  superseded_by_id: null,
  supersedes_ids: [],
  depends_on_ids: [],
  is_blocked: kind === "task" ? false : null,
  source: "user",
  source_agent_run_id: null,
  stage_key: null,
  created_at: "2026-11-20T10:00:00Z",
  updated_at: "2026-11-20T10:00:00Z",
  ...extra,
});

export function plan(taskCount = 3): Plan {
  return {
    tasks: Array.from({ length: taskCount }, (_, i) => ({
      title: `Task ${i}`,
      description: `Do part ${i}.`,
      priority: "medium" as const,
      acceptance_criteria: [`Part ${i} works`],
      depends_on: i > 0 ? [i - 1] : [],
      possible_duplicate_of: null,
    })),
    decisions: [
      {
        title: "Use argon2",
        what: "Hash passwords with argon2.",
        why: "Slow to brute force.",
        alternatives: "bcrypt",
      },
    ],
    assumptions: ["Users have email"],
    risks: ["Lockout abuse"],
    open_questions: ["Do we need SSO?"],
  };
}

export const review = (verdict: Review["verdict"] = "changes_requested"): Review => ({
  verdict,
  findings: [
    {
      severity: "high",
      refers_to: ["task:1", REQ_ID],
      explanation: "Task 1 has no rate limit.",
      suggestion: "Add one.",
    },
  ],
});

export function agentRun(status: string, extra: Partial<AgentRun> = {}): AgentRun {
  return {
    id: RUN_ID,
    project_id: PROJECT_ID,
    run_type: "plan",
    status,
    stage_id: "requirements",
    model_id: MODEL_SMALL,
    prompt_version: "planner_v1,reviewer_v1",
    input: { requirement_id: REQ_ID, requirement_text: null, use_code_context: false },
    estimate: {
      steps: 2,
      input_tokens: 2000,
      output_tokens: 8000,
      cost_usd: "0.018",
      cost_limit_usd: "0.50",
      model: "google/Small Model",
    },
    result: {},
    warnings: [],
    error: null,
    error_message: null,
    error_details: {},
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: null,
    cancel_requested_at: null,
    created_at: "2026-11-20T10:00:00Z",
    started_at: null,
    finished_at: null,
    decided_at: null,
    decision_reason: null,
    saved_item_ids: [],
    steps: [],
    ...extra,
  };
}

export const waitingRun = (taskCount = 3, extra: Partial<AgentRun> = {}): AgentRun =>
  agentRun("waiting_for_approval", {
    result: { plan: plan(taskCount), review: review() },
    input_tokens: 1800,
    output_tokens: 900,
    cost_usd: "0.0042",
    ...extra,
  });
