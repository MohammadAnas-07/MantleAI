// Names for the generated schema types, plus hand-written types for the few responses the
// backend declares only as `dict` (OpenAPI shows them as untyped objects). Those are listed
// as API gaps; keep them in step with the backend by hand until it declares real models.

import type { components } from "./schema";

type Schemas = components["schemas"];

export type Project = Schemas["ProjectOut"];
export type ProjectCreate = Schemas["ProjectCreate"];
export type ProjectPatch = Schemas["ProjectPatch"];
export type IndexStatus = Schemas["IndexStatusOut"];
export type IndexRun = Schemas["RunOut"];
export type ProjectProfile = Schemas["ProjectProfileOut"];
export type RunStarted = Schemas["RunStarted"];
export type DocumentPage = Schemas["DocumentPageOut"];
export type IndexedFile = Schemas["DocumentOut"];
export type Provider = Schemas["ProviderOut"];
export type Credential = Schemas["CredentialOut"];
export type CredentialTest = Schemas["CredentialTestOut"];
export type Model = Schemas["ModelOut"];
export type ModelSettings = Schemas["ModelSettingsOut"];
export type ModelSettingsPatch = Schemas["ModelSettingsPatch"];
export type Usage = Schemas["UsageOut"];
export type UsageLine = Schemas["UsageLine"];
export type UsageRecord = Schemas["UsageRecordOut"];
export type Conversation = Schemas["ConversationOut"];
export type Message = Schemas["MessageOut"];
export type Handoff = Schemas["HandoffOut"];
export type MemoryItem = Schemas["MemoryItemOut"];
export type MemoryPage = Schemas["MemoryPage"];
export type MemoryCreate = Schemas["MemoryItemCreate"];
export type MemoryPatch = Schemas["MemoryItemPatch"];
export type Workflow = Schemas["WorkflowOut"];
export type Stage = Schemas["StageOut"];
export type WorkflowEvent = Schemas["WorkflowEventOut"];
export type Unmet = Schemas["UnmetOut"];
export type AgentRun = Schemas["AgentRunOut"];
export type AgentRunPage = Schemas["AgentRunPage"];
/** A plan or review run in a list: no plan, review, input or steps (GET /agent-runs/{id}). */
export type AgentRunSummary = Schemas["AgentRunSummaryOut"];
export type AgentRunSummaryPage = Schemas["AgentRunSummaryPage"];
export type AgentRunStart = Schemas["AgentRunIn"];
export type AgentRunEstimate = Schemas["AgentRunEstimateOut"];
export type ApproveRunBody = Schemas["ApproveRunIn"];
export type ApproveRunResult = Schemas["ApproveRunOut"];

export type MemoryKind = "requirement" | "decision" | "task";

// ---- untyped on the backend (dict responses) -----------------------------------------------

export interface SuggestedModel {
  model_id: string;
  display_name: string;
  provider: string;
  context_window: number;
}

export interface SourceReport {
  path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  score: number;
  vector_rank: number | null;
  text_rank: number | null;
  chunk_ids: string[];
}

export interface DroppedSource extends SourceReport {
  reason: "share" | "context_budget";
}

export interface ContextSection {
  name: string;
  included: boolean;
  tokens: number;
  items_total: number;
  items_included: number;
  content: string | { role: string; content: string }[];
}

export interface HandoffPreview {
  model_id: string;
  model: string;
  context_window: number;
  reserved_output_tokens: number;
  safety_margin_tokens: number;
  budget: number;
  total_tokens: number;
  sections: ContextSection[];
  dropped: string[];
  pinned: {
    tokens: number;
    max_tokens: number;
    included: number;
    dropped: { id: string; kind: string; reason: string }[];
  };
  retrieved: {
    tokens: number;
    max_tokens: number;
    used: SourceReport[];
    dropped: DroppedSource[];
  };
  // The project profile section: fields sent, and fields left out with the reason
  // (profile_budget: over CONTEXT_PROFILE_MAX_TOKENS; context_budget: the whole request).
  profile: {
    tokens: number;
    max_tokens: number;
    fields: string[];
    dropped: { field: string; reason: string }[];
  };
  has_key: boolean;
  will_build_summary: boolean;
  summary_input_tokens: number;
}

export interface HandoffNote {
  text: string;
  from_model: string;
  to_model: string;
  dropped: string[];
}

export interface SwitchResult {
  conversation: Conversation;
  handoff: Handoff;
  preview: HandoffPreview;
}

export interface SkipReport {
  [reason: string]: { count: number; examples: string[] };
}

export interface IndexEstimate {
  files_total: number;
  files_to_index: number;
  files_unchanged: number;
  files_skipped: number;
  files_deleted: number;
  segments_to_embed: number;
  segments_reused: number;
  tokens: number;
  cost_usd: string | null;
  cost_limit_usd: string;
  provider: string;
  model: string;
  skip_report: SkipReport;
}

// ---- agent run results (AgentRunOut.result, .estimate and .warnings are dicts) -------------
// Shapes from backend/app/modules/workflow/outputs.py and run_setup.estimate. Model output:
// every string here is untrusted and is rendered as plain text.

export type Severity = "low" | "medium" | "high";

export interface GapFinding {
  title: string;
  explanation: string;
  severity: Severity;
  refers_to: string[];
}

export interface GapReport {
  missing_steps: GapFinding[];
  risks: GapFinding[];
  technical_debt: GapFinding[];
  scalability_concerns: GapFinding[];
}

export interface ProposedTask {
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  acceptance_criteria: string[];
  depends_on: number[];
  possible_duplicate_of: string | null;
}

export interface ProposedDecision {
  title: string;
  what: string;
  why: string;
  alternatives: string;
}

export interface Plan {
  tasks: ProposedTask[];
  decisions: ProposedDecision[];
  assumptions: string[];
  risks: string[];
  open_questions: string[];
}

export interface ReviewFinding {
  severity: Severity;
  refers_to: string[];
  explanation: string;
  suggestion: string;
}

export interface Review {
  verdict: "approve" | "changes_requested";
  findings: ReviewFinding[];
}

/** The estimate stored on a run and sent with a 409 cost_limit_exceeded. */
export interface RunEstimate {
  steps: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string | null;
  cost_limit_usd: string;
  model: string;
}

export interface RunWarning {
  code: string;
  [key: string]: unknown;
}

// ---- the chat stream (SSE) -----------------------------------------------------------------

export interface StreamStart {
  message_id: string;
  user_message_id: string;
  conversation_id: string;
  model_id: string;
  sources: SourceReport[];
}

export interface StreamWarning {
  message_id: string;
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface StreamEnd {
  message_id: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cost_usd: string | null;
    latency_ms: number;
  };
}

export interface StreamError {
  message_id: string;
  code: string;
  message: string;
  details: { suggested_models?: SuggestedModel[] } & Record<string, unknown>;
}

export type StreamEvent =
  | { type: "message_start"; data: StreamStart }
  | { type: "delta"; data: { text: string } }
  | { type: "warning"; data: StreamWarning }
  | { type: "message_end"; data: StreamEnd }
  | { type: "error"; data: StreamError };
