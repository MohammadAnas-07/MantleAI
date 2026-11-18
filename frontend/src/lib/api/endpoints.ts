// Typed calls for every endpoint the UI uses. Paths and bodies follow docs/api-outline.md.

import { apiFetch, apiRequest } from "./client";
import { ApiError, CLIENT_CODES } from "./errors";
import { readSse, type SseMessage } from "./sse";
import type {
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
  ProjectPatch,
  Provider,
  RunStarted,
  StreamEvent,
  SwitchResult,
  Usage,
  UsageRecord,
} from "./types";

type Opts = { signal?: AbortSignal };

export const api = {
  health: (o: Opts = {}) =>
    apiFetch<{ status: string; database: string }>("/health", { ...o, timeoutMs: 5_000 }),

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
