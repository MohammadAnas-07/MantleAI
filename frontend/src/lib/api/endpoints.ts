// Typed calls for every endpoint the UI uses. Paths and bodies follow docs/api-outline.md.

import { apiFetch, apiRequest } from "./client";
import { ApiError, CLIENT_CODES } from "./errors";
import { readSse, type SseMessage } from "./sse";
import type {
  AgentRun,
  AgentRunEstimate,
  AgentRunPage,
  AgentRunSummaryPage,
  AgentRunStart,
  ApproveRunBody,
  ApproveRunResult,
  Conversation,
  Credential,
  CredentialTest,
  DocumentPage,
  Handoff,
  HandoffPreview,
  IndexEstimate,
  IndexRun,
  IndexStatus,
  MemoryCreate,
  MemoryItem,
  MemoryKind,
  MemoryPage,
  MemoryPatch,
  Message,
  Model,
  ModelSettings,
  ModelSettingsPatch,
  Project,
  ProjectCreate,
  ProjectProfile,
  ProjectPatch,
  Provider,
  RunStarted,
  StreamEvent,
  SwitchResult,
  Usage,
  UsageRecord,
  Workflow,
} from "./types";

type Opts = { signal?: AbortSignal };

// The gap finder answers in the same request: up to two model calls of at most
// AGENT_STEP_TIMEOUT_SECONDS (180 s) each.
const GAP_FINDER_TIMEOUT_MS = 420_000;

export const api = {
  health: (o: Opts = {}) =>
    // keys: none | ok | unreadable (the master key can't decrypt a saved key) | unknown
    apiFetch<{ status: string; database: string; keys?: string }>("/health", {
      ...o,
      timeoutMs: 5_000,
    }),

  // ---- settings ----
  providers: (o: Opts = {}) => apiFetch<Provider[]>("/api/v1/providers", o),
  credentials: (o: Opts = {}) => apiFetch<Credential[]>("/api/v1/credentials", o),
  addCredential: (body: { provider: string; label: string; api_key: string }) =>
    apiFetch<Credential>("/api/v1/credentials", { method: "POST", body }),
  testCredential: (id: string) =>
    apiFetch<CredentialTest>(`/api/v1/credentials/${id}/test`, { method: "POST", body: {} }),
  deleteCredential: (id: string) =>
    apiFetch<undefined>(`/api/v1/credentials/${id}`, { method: "DELETE" }),
  models: (o: Opts = {}) => apiFetch<Model[]>("/api/v1/models", o),
  updateModel: (id: string, body: { enabled?: boolean; context_window?: number }) =>
    apiFetch<Model>(`/api/v1/models/${id}`, { method: "PATCH", body }),
  modelSettings: (o: Opts = {}) => apiFetch<ModelSettings>("/api/v1/settings/models", o),
  updateModelSettings: (body: ModelSettingsPatch) =>
    apiFetch<ModelSettings>("/api/v1/settings/models", { method: "PATCH", body }),
  usage: (o: Opts = {}) => apiFetch<Usage>("/api/v1/usage", o),
  usageRecords: (since: string, o: Opts = {}) =>
    apiFetch<UsageRecord[]>("/api/v1/usage/records", { ...o, query: { since, limit: 200 } }),

  // ---- projects ----
  projects: (o: Opts = {}) => apiFetch<Project[]>("/api/v1/projects", o),
  project: (id: string, o: Opts = {}) => apiFetch<Project>(`/api/v1/projects/${id}`, o),
  createProject: (body: ProjectCreate) =>
    apiFetch<Project>("/api/v1/projects", { method: "POST", body }),
  updateProject: (id: string, body: ProjectPatch) =>
    apiFetch<Project>(`/api/v1/projects/${id}`, { method: "PATCH", body }),
  deleteProject: (id: string) =>
    apiFetch<undefined>(`/api/v1/projects/${id}`, { method: "DELETE" }),

  setSource: (id: string, rootPath: string) =>
    apiFetch<IndexStatus>(`/api/v1/projects/${id}/source`, {
      method: "PUT",
      body: { root_path: rootPath },
    }),

  // ---- index ----
  indexStatus: (id: string, o: Opts = {}) =>
    apiFetch<IndexStatus>(`/api/v1/projects/${id}/index`, o),
  estimate: (id: string) =>
    apiFetch<IndexEstimate>(`/api/v1/projects/${id}/index/estimate`, {
      method: "POST",
      body: {},
      timeoutMs: 120_000, // reads the whole folder
    }),
  startIndex: (id: string, force: boolean) =>
    apiFetch<RunStarted>(`/api/v1/projects/${id}/index`, {
      method: "POST",
      body: { force },
      timeoutMs: 120_000,
    }),
  run: (runId: string, o: Opts = {}) => apiFetch<IndexRun>(`/api/v1/index-runs/${runId}`, o),
  profile: (id: string, o: Opts = {}) =>
    apiFetch<ProjectProfile>(`/api/v1/projects/${id}/profile`, o),
  cancelRun: (runId: string) =>
    apiFetch<IndexRun>(`/api/v1/index-runs/${runId}/cancel`, { method: "POST", body: {} }),
  documents: (id: string, status: string | null, o: Opts = {}) =>
    apiFetch<DocumentPage>(`/api/v1/projects/${id}/documents`, {
      ...o,
      query: { status, limit: 500 },
    }),
  deleteIndex: (id: string) =>
    apiFetch<undefined>(`/api/v1/projects/${id}/index`, { method: "DELETE" }),

  // ---- memory ----
  memory: (projectId: string, kind: MemoryKind, o: Opts = {}) =>
    apiFetch<MemoryPage>(`/api/v1/projects/${projectId}/memory`, {
      ...o,
      query: { kind, limit: 100 },
    }),
  createMemory: (projectId: string, body: MemoryCreate) =>
    apiFetch<MemoryItem>(`/api/v1/projects/${projectId}/memory`, { method: "POST", body }),
  updateMemory: (id: string, body: MemoryPatch) =>
    apiFetch<MemoryItem>(`/api/v1/memory/${id}`, { method: "PATCH", body }),
  memoryItem: (id: string, o: Opts = {}) => apiFetch<MemoryItem>(`/api/v1/memory/${id}`, o),
  deleteMemory: (id: string) => apiFetch<undefined>(`/api/v1/memory/${id}`, { method: "DELETE" }),
  supersede: (
    id: string,
    body: { by_id: string } | { decision: { title: string; body?: string; why?: string } },
  ) =>
    apiFetch<{ superseded: MemoryItem; by: MemoryItem }>(`/api/v1/memory/${id}/supersede`, {
      method: "POST",
      body,
    }),
  addDependency: (taskId: string, dependsOnId: string) =>
    apiFetch<MemoryItem>(`/api/v1/memory/${taskId}/dependencies`, {
      method: "POST",
      body: { depends_on_id: dependsOnId },
    }),
  removeDependency: (taskId: string, dependsOnId: string) =>
    apiFetch<undefined>(`/api/v1/memory/${taskId}/dependencies/${dependsOnId}`, {
      method: "DELETE",
    }),

  // ---- conversations ----
  conversations: (projectId: string, o: Opts = {}) =>
    apiFetch<Conversation[]>(`/api/v1/projects/${projectId}/conversations`, o),
  conversation: (id: string, o: Opts = {}) =>
    apiFetch<Conversation>(`/api/v1/conversations/${id}`, o),
  createConversation: (projectId: string, body: { model_id: string; title?: string }) =>
    apiFetch<Conversation>(`/api/v1/projects/${projectId}/conversations`, {
      method: "POST",
      body,
    }),
  updateConversation: (id: string, body: { title?: string; code_context_enabled?: boolean }) =>
    apiFetch<Conversation>(`/api/v1/conversations/${id}`, { method: "PATCH", body }),
  messages: (id: string, o: Opts = {}) =>
    apiFetch<Message[]>(`/api/v1/conversations/${id}/messages`, { ...o, query: { limit: 500 } }),
  handoffPreview: (id: string, modelId: string, o: Opts = {}) =>
    apiFetch<HandoffPreview>(`/api/v1/conversations/${id}/handoff-preview`, {
      ...o,
      query: { model_id: modelId },
    }),
  switchModel: (id: string, modelId: string, reason = "user_choice") =>
    apiFetch<SwitchResult>(`/api/v1/conversations/${id}/switch-model`, {
      method: "POST",
      body: { model_id: modelId, reason },
      timeoutMs: 120_000, // may write a summary with the new model
    }),
  handoffs: (id: string, o: Opts = {}) =>
    apiFetch<Handoff[]>(`/api/v1/conversations/${id}/handoffs`, o),

  // ---- workflow ----
  // Approve and skip always send the stage the user is looking at: if another tab moved the
  // workflow first, the backend answers 409 workflow_changed instead of acting on the next one.
  workflow: (projectId: string, o: Opts = {}) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow`, o),
  setChecklistItem: (
    projectId: string,
    body: { stage_id: string; item_id: string; done: boolean },
  ) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow/checklist`, {
      method: "POST",
      body,
    }),
  approveStage: (projectId: string, body: { stage_id: string; force?: boolean; reason?: string }) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow/approve`, { method: "POST", body }),
  skipStage: (projectId: string, body: { stage_id: string; reason: string }) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow/skip`, { method: "POST", body }),
  reopenStage: (projectId: string, body: { stage_id: string; reason: string }) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow/reopen`, { method: "POST", body }),
  resetWorkflow: (projectId: string, reason: string) =>
    apiFetch<Workflow>(`/api/v1/projects/${projectId}/workflow/reset`, {
      method: "POST",
      body: { reason },
    }),

  // ---- gap finder and agent runs ----
  runGapFinder: (projectId: string, body: { model_id: string; force: boolean }) =>
    apiFetch<AgentRun>(`/api/v1/projects/${projectId}/gap-finder`, {
      method: "POST",
      body,
      timeoutMs: GAP_FINDER_TIMEOUT_MS,
    }),
  gapRuns: (projectId: string, o: Opts = {}) =>
    apiFetch<AgentRunPage>(`/api/v1/projects/${projectId}/gap-finder`, o),
  estimateAgentRun: (projectId: string, body: AgentRunStart) =>
    apiFetch<AgentRunEstimate>(`/api/v1/projects/${projectId}/agent-runs/estimate`, {
      method: "POST",
      body,
      timeoutMs: 60_000, // counts prompt tokens
    }),
  startAgentRun: (projectId: string, body: AgentRunStart) =>
    apiFetch<AgentRun>(`/api/v1/projects/${projectId}/agent-runs`, {
      method: "POST",
      body,
      timeoutMs: 60_000,
    }),
  agentRuns: (projectId: string, o: Opts = {}) =>
    apiFetch<AgentRunSummaryPage>(`/api/v1/projects/${projectId}/agent-runs`, o),
  agentRun: (runId: string, o: Opts = {}) => apiFetch<AgentRun>(`/api/v1/agent-runs/${runId}`, o),
  cancelAgentRun: (runId: string) =>
    apiFetch<AgentRun>(`/api/v1/agent-runs/${runId}/cancel`, { method: "POST", body: {} }),
  approveAgentRun: (runId: string, body: ApproveRunBody) =>
    apiFetch<ApproveRunResult>(`/api/v1/agent-runs/${runId}/approve`, { method: "POST", body }),
  rejectAgentRun: (runId: string, reason: string) =>
    apiFetch<AgentRun>(`/api/v1/agent-runs/${runId}/reject`, {
      method: "POST",
      body: { reason },
    }),
};

const STREAM_EVENTS = new Set(["message_start", "delta", "warning", "message_end", "error"]);

/** Parse one SSE message into a typed event; unknown or malformed events are skipped. */
export function toStreamEvent(message: SseMessage): StreamEvent | null {
  if (!STREAM_EVENTS.has(message.event)) return null;
  let data: unknown;
  try {
    data = JSON.parse(message.data);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  return { type: message.event, data } as StreamEvent;
}

/**
 * Send a chat message and stream the reply. HTTP errors before the stream starts (409 a reply
 * is already running, 413 context too long with suggested_models) reject as ApiError.
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await apiRequest(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: { content },
    signal,
    // Only the wait for the first byte is timed: retrieval may embed the query first.
    timeoutMs: 90_000,
  });
  if (!response.body) {
    throw new ApiError(response.status, CLIENT_CODES.badResponse, "The reply had no body.");
  }
  await readSse(
    response.body,
    (message) => {
      const event = toStreamEvent(message);
      if (event) onEvent(event);
    },
    signal,
  );
}
