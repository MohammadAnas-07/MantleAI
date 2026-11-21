// Small, fixed API answers for component tests. Shapes follow the generated schema types.

import type {
  Conversation,
  HandoffPreview,
  Message,
  Model,
  Project,
  Provider,
} from "../lib/api/types";

export const API = "http://127.0.0.1:8000";

export const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
export const CONV_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const CONV_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
export const MODEL_SMALL = "00000000-0000-4000-8000-000000000001";
export const MODEL_BIG = "00000000-0000-4000-8000-000000000002";

const model = (id: string, name: string, window: number, provider: string): Model => ({
  id,
  provider,
  litellm_model: `${provider}/${name}`,
  display_name: name,
  kind: "chat",
  context_window: window,
  max_output_tokens: 4096,
  embedding_dimensions: null,
  supports_tools: false,
  input_cost_per_mtok: "1",
  output_cost_per_mtok: "2",
  enabled: true,
});

export const models: Model[] = [
  model(MODEL_SMALL, "Small Model", 8_000, "google"),
  model(MODEL_BIG, "Big Model", 1_000_000, "openai"),
];

export const providers: Provider[] = [
  { id: "google", name: "Google", supports_chat: true, supports_embeddings: true, has_key: true },
  { id: "openai", name: "OpenAI", supports_chat: true, supports_embeddings: true, has_key: true },
];

export const project: Project = {
  id: PROJECT_ID,
  name: "Demo project",
  description: null,
  root_path: "C:\\code\\demo",
  default_model_id: MODEL_SMALL,
  indexed: false,
  last_indexed_at: null,
  needs_reindex: false,
  reindex_reasons: [],
};

export const conversation = (id: string, title: string, modelId = MODEL_SMALL): Conversation => ({
  id,
  project_id: PROJECT_ID,
  title,
  current_model_id: modelId,
  generating: false,
  summary_error: null,
  code_context_enabled: true,
  created_at: "2026-11-18T10:00:00Z",
  updated_at: "2026-11-18T10:00:00Z",
});

export const message = (
  id: string,
  sequence: number,
  role: string,
  text: string,
  status = "complete",
): Message => ({
  id,
  sequence,
  role,
  content: [{ type: "text", text }],
  model_id: role === "assistant" ? MODEL_SMALL : null,
  status,
  error_code: null,
  token_count: 1,
  input_tokens: null,
  output_tokens: null,
  created_at: "2026-11-18T10:00:00Z",
});

export const preview = (modelId: string, hasKey = true): HandoffPreview => ({
  model_id: modelId,
  model: "Big Model",
  context_window: 1_000_000,
  reserved_output_tokens: 4096,
  safety_margin_tokens: 100_000,
  budget: 895_904,
  total_tokens: 1_200,
  sections: [
    { name: "system", included: true, tokens: 300, items_total: 0, items_included: 0, content: "" },
    {
      name: "retrieved_context",
      included: true,
      tokens: 400,
      items_total: 1,
      items_included: 1,
      content: "",
    },
  ],
  dropped: [],
  pinned: { tokens: 0, max_tokens: 1000, included: 0, dropped: [] },
  profile: { tokens: 0, max_tokens: 600, fields: [], dropped: [] },
  retrieved: {
    tokens: 400,
    max_tokens: 268_771,
    used: [
      {
        path: "app/main.py",
        start_line: 10,
        end_line: 42,
        symbol: "health",
        score: 0.0328,
        vector_rank: 1,
        text_rank: 2,
        chunk_ids: ["c1"],
      },
    ],
    dropped: [],
  },
  has_key: hasKey,
  will_build_summary: false,
  summary_input_tokens: 0,
});

/** An SSE body: `event: name\ndata: json\n\n` for each event. */
export function sse(...events: [string, unknown][]): string {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
}

export function apiError(code: string, message: string, details: Record<string, unknown> = {}) {
  return { error: { code, message, details } };
}
