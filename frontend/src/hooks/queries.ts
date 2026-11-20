// TanStack Query hooks. Every key includes the ids it depends on, so switching project or
// conversation never shows the previous one's data, and the request for the old key is
// aborted through the signal TanStack passes in.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api/endpoints";
import type { AgentRun, IndexRun, Message, MemoryKind } from "../lib/api/types";

export const keys = {
  health: ["health"] as const,
  providers: ["providers"] as const,
  credentials: ["credentials"] as const,
  models: ["models"] as const,
  modelSettings: ["model-settings"] as const,
  usage: ["usage"] as const,
  usageRecords: (since: string) => ["usage-records", since] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  indexStatus: (id: string) => ["index-status", id] as const,
  run: (id: string) => ["run", id] as const,
  documents: (id: string, status: string | null) => ["documents", id, status] as const,
  memory: (projectId: string, kind: MemoryKind) => ["memory", projectId, kind] as const,
  conversations: (projectId: string) => ["conversations", projectId] as const,
  conversation: (id: string) => ["conversation", id] as const,
  messages: (id: string) => ["messages", id] as const,
  preview: (id: string, modelId: string) => ["preview", id, modelId] as const,
  memoryItem: (id: string) => ["memory-item", id] as const,
  workflow: (projectId: string) => ["workflow", projectId] as const,
  gapRuns: (projectId: string) => ["gap-runs", projectId] as const,
  agentRuns: (projectId: string) => ["agent-runs", projectId] as const,
  // The project is part of the key, so a poll that answers after a project switch lands in
  // the old project's cache entry and never in the new one's.
  agentRun: (projectId: string, runId: string) => ["agent-run", projectId, runId] as const,
};

export const useHealth = () =>
  useQuery({
    queryKey: keys.health,
    queryFn: ({ signal }) => api.health({ signal }),
    refetchInterval: 15_000,
    retry: false,
  });

export const useProviders = () =>
  useQuery({ queryKey: keys.providers, queryFn: ({ signal }) => api.providers({ signal }) });

export const useCredentials = () =>
  useQuery({ queryKey: keys.credentials, queryFn: ({ signal }) => api.credentials({ signal }) });

export const useModels = () =>
  useQuery({ queryKey: keys.models, queryFn: ({ signal }) => api.models({ signal }) });

export const useModelSettings = () =>
  useQuery({
    queryKey: keys.modelSettings,
    queryFn: ({ signal }) => api.modelSettings({ signal }),
  });

export const useUsage = () =>
  useQuery({ queryKey: keys.usage, queryFn: ({ signal }) => api.usage({ signal }) });

export const useUsageRecords = (since: string) =>
  useQuery({
    queryKey: keys.usageRecords(since),
    queryFn: ({ signal }) => api.usageRecords(since, { signal }),
    refetchInterval: 10_000,
  });

export const useProjects = () =>
  useQuery({ queryKey: keys.projects, queryFn: ({ signal }) => api.projects({ signal }) });

export const useProject = (id: string | undefined) =>
  useQuery({
    queryKey: keys.project(id ?? ""),
    queryFn: ({ signal }) => api.project(id ?? "", { signal }),
    enabled: Boolean(id),
  });

export const useIndexStatus = (id: string) =>
  useQuery({
    queryKey: keys.indexStatus(id),
    queryFn: ({ signal }) => api.indexStatus(id, { signal }),
  });

export const isActiveRun = (run: IndexRun | undefined): boolean =>
  run?.status === "queued" || run?.status === "running";

export const useRun = (runId: string | null) =>
  useQuery({
    queryKey: keys.run(runId ?? ""),
    queryFn: ({ signal }) => api.run(runId ?? "", { signal }),
    enabled: Boolean(runId),
    // Poll while the job runs; stop as soon as it reaches an end state.
    refetchInterval: (query) => (isActiveRun(query.state.data) ? 1_500 : false),
  });

export const useDocuments = (id: string, status: string | null) =>
  useQuery({
    queryKey: keys.documents(id, status),
    queryFn: ({ signal }) => api.documents(id, status, { signal }),
  });

export const useMemory = (projectId: string, kind: MemoryKind) =>
  useQuery({
    queryKey: keys.memory(projectId, kind),
    queryFn: ({ signal }) => api.memory(projectId, kind, { signal }),
  });

export const useConversations = (projectId: string) =>
  useQuery({
    queryKey: keys.conversations(projectId),
    queryFn: ({ signal }) => api.conversations(projectId, { signal }),
  });

export const useConversation = (id: string) =>
  useQuery({
    queryKey: keys.conversation(id),
    queryFn: ({ signal }) => api.conversation(id, { signal }),
  });

const stillStreaming = (messages: Message[] | undefined): boolean =>
  Boolean(messages?.some((m) => m.status === "streaming"));

export const useMessages = (id: string) =>
  useQuery({
    queryKey: keys.messages(id),
    queryFn: ({ signal }) => api.messages(id, { signal }),
    // After a stop the backend saves the partial reply a moment later: poll until it has.
    refetchInterval: (query) => (stillStreaming(query.state.data) ? 1_000 : false),
  });

export const useHandoffPreview = (id: string, modelId: string | null) =>
  useQuery({
    queryKey: keys.preview(id, modelId ?? ""),
    queryFn: ({ signal }) => api.handoffPreview(id, modelId ?? "", { signal }),
    enabled: Boolean(modelId),
  });

export const useMemoryItem = (id: string) =>
  useQuery({
    queryKey: keys.memoryItem(id),
    queryFn: ({ signal }) => api.memoryItem(id, { signal }),
  });

export const useWorkflow = (projectId: string) =>
  useQuery({
    queryKey: keys.workflow(projectId),
    queryFn: ({ signal }) => api.workflow(projectId, { signal }),
  });

export const useGapRuns = (projectId: string) =>
  useQuery({
    queryKey: keys.gapRuns(projectId),
    queryFn: ({ signal }) => api.gapRuns(projectId, { signal }),
  });

export const useAgentRuns = (projectId: string) =>
  useQuery({
    queryKey: keys.agentRuns(projectId),
    queryFn: ({ signal }) => api.agentRuns(projectId, { signal }),
  });

/** Queued or running: the backend may still change it on its own. */
export const isRunActive = (run: AgentRun | undefined): boolean =>
  run?.status === "queued" || run?.status === "running";

export const AGENT_RUN_POLL_MS = 1_500;

export const useAgentRun = (projectId: string, runId: string | null) =>
  useQuery({
    queryKey: keys.agentRun(projectId, runId ?? ""),
    queryFn: ({ signal }) => api.agentRun(runId ?? "", { signal }),
    enabled: Boolean(runId),
    // Poll while the job runs; stop at waiting_for_approval or any end state. TanStack stops
    // polling on unmount and aborts the request in flight through `signal`.
    refetchInterval: (query) => (isRunActive(query.state.data) ? AGENT_RUN_POLL_MS : false),
  });
