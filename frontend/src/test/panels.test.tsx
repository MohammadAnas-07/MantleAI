import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { KeysSection } from "../features/settings/KeysSection";
import type { IndexRun, MemoryItem } from "../lib/api/types";
import {
  API,
  apiError,
  CONV_A,
  conversation,
  MODEL_BIG,
  PROJECT_ID,
  preview,
  project,
} from "./fixtures";
import { renderApp, renderWithClient } from "./render";
import { server } from "./server";

describe("model switch", () => {
  it("previews, switches on confirm and shows the handoff note", async () => {
    const switched = vi.fn();
    server.use(
      http.get(`${API}/api/v1/conversations/${CONV_A}/handoff-preview`, () =>
        HttpResponse.json(preview(MODEL_BIG)),
      ),
      http.post(`${API}/api/v1/conversations/${CONV_A}/switch-model`, async ({ request }) => {
        switched(await request.json());
        return HttpResponse.json({
          conversation: conversation(CONV_A, "Chat", MODEL_BIG),
          handoff: {
            id: "h1",
            from_model_id: "x",
            to_model_id: MODEL_BIG,
            reason: "user_choice",
            conversation_summary_id: null,
            first_raw_message_id: null,
            tokens_before: 1,
            tokens_after: 1,
            created_at: "2026-11-18T10:00:00Z",
            note: {
              text: "Switched from Small Model to Big Model. 4 messages carried verbatim.",
              dropped: [],
            },
          },
          preview: preview(MODEL_BIG),
        });
      }),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}/c/${CONV_A}`);
    const select = await screen.findByRole("combobox", { name: "Model" });
    await waitFor(() => {
      expect(within(select).getAllByRole("option")).toHaveLength(2);
    });
    await user.selectOptions(select, MODEL_BIG);
    const dialog = await screen.findByRole("dialog", { name: "Switch to Big Model" });
    expect(await within(dialog).findByText(/1\.2k of 895\.9k tokens/)).toBeInTheDocument();
    expect(switched).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Switch" }));
    expect(await screen.findByText(/4 messages carried verbatim/)).toBeInTheDocument();
    expect(switched).toHaveBeenCalledWith({ model_id: MODEL_BIG, reason: "user_choice" });
  });
});

function storedText(storage: Storage): string {
  return Object.keys(storage)
    .map((key) => `${key}=${storage.getItem(key) ?? ""}`)
    .join("\n");
}

describe("provider key form", () => {
  it("clears the key after submit and never stores it", async () => {
    const KEY = "sk-test-not-a-real-key-12345678";
    let sent: unknown = null;
    server.use(
      http.get(`${API}/api/v1/credentials`, () => HttpResponse.json([])),
      http.post(`${API}/api/v1/credentials`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          id: "c1",
          provider: "google",
          label: "",
          key_hint: "5678",
          last_tested_at: null,
          last_test_ok: null,
          created_at: "2026-11-18T10:00:00Z",
        });
      }),
    );
    const log = vi.spyOn(console, "log");
    const { user } = renderWithClient(<KeysSection />);
    const input = await screen.findByLabelText("API key");
    expect(input).toHaveAttribute("type", "password");
    await user.type(input, KEY);
    await user.click(screen.getByRole("button", { name: "Save key" }));
    await waitFor(() => {
      expect(sent).toMatchObject({ provider: "google", api_key: KEY });
    });
    expect(input).toHaveValue("");
    expect(storedText(localStorage)).not.toContain(KEY);
    expect(storedText(sessionStorage)).not.toContain(KEY);
    expect(window.location.href).not.toContain(KEY);
    expect(document.body.innerHTML).not.toContain(KEY);
    expect(log).not.toHaveBeenCalled();
  });

  it("clears the key even when the backend refuses it", async () => {
    server.use(
      http.get(`${API}/api/v1/credentials`, () => HttpResponse.json([])),
      http.post(`${API}/api/v1/credentials`, () =>
        HttpResponse.json(apiError("validation_error", "Invalid request."), { status: 422 }),
      ),
    );
    const { user } = renderWithClient(<KeysSection />);
    const input = await screen.findByLabelText("API key");
    await user.type(input, "sk-test-bad-key-000000");
    await user.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByText("Invalid request.")).toBeInTheDocument();
    expect(input).toHaveValue("");
  });
});

const run = (status: string, extra: Partial<IndexRun> = {}): IndexRun => ({
  id: "r1",
  project_id: PROJECT_ID,
  status,
  error: null,
  files_seen: 16,
  files_indexed: status === "succeeded" ? 16 : 0,
  files_skipped: 0,
  files_unchanged: 0,
  chunks_created: 28,
  tokens: 3289,
  cost_estimate_usd: "0.000493",
  force: true,
  embedding_model: "gemini/gemini-embedding-001",
  root_path: "C:\\code\\demo",
  estimate: {},
  skip_report: {},
  created_at: "2026-11-18T10:00:00Z",
  started_at: null,
  finished_at: null,
  cancel_requested_at: null,
  ...extra,
});

const ESTIMATE = {
  files_total: 16,
  files_to_index: 16,
  files_unchanged: 0,
  files_skipped: 2,
  files_deleted: 0,
  segments_to_embed: 28,
  segments_reused: 0,
  tokens: 3289,
  cost_usd: "1.50",
  cost_limit_usd: "1.00",
  provider: "google",
  model: "gemini/gemini-embedding-001",
  skip_report: {},
};

function indexHandlers(runStatuses: string[], startCalls: boolean[]) {
  let polls = 0;
  return [
    http.get(`${API}/api/v1/projects/${PROJECT_ID}/index`, () =>
      HttpResponse.json({
        project_id: PROJECT_ID,
        root_path: "C:\\code\\demo",
        indexed: false,
        last_indexed_at: null,
        needs_reindex: true,
        reindex_reasons: ["embedding_model_changed"],
        embedding_models: [],
        files: 0,
        active_run_id: null,
      }),
    ),
    http.post(`${API}/api/v1/projects/${PROJECT_ID}/index/estimate`, () =>
      HttpResponse.json(ESTIMATE),
    ),
    http.post(`${API}/api/v1/projects/${PROJECT_ID}/index`, async ({ request }) => {
      const { force } = (await request.json()) as { force: boolean };
      startCalls.push(force);
      if (!force) {
        return HttpResponse.json(
          apiError("cost_limit_exceeded", "Indexing would cost about $1.50.", {
            estimate: ESTIMATE,
          }),
          { status: 409 },
        );
      }
      return HttpResponse.json(
        { run_id: "r1", status: "queued", estimate: ESTIMATE },
        { status: 202 },
      );
    }),
    http.get(`${API}/api/v1/index-runs/r1`, () => {
      const status = runStatuses[Math.min(polls, runStatuses.length - 1)] ?? "running";
      polls += 1;
      return HttpResponse.json(run(status));
    }),
    http.get(`${API}/api/v1/projects/${PROJECT_ID}/documents`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0, counts: {} }),
    ),
  ];
}

async function openIndexTab(user: ReturnType<typeof renderApp>["user"]) {
  await user.click(await screen.findByRole("tab", { name: "Index" }));
}

describe("index panel", () => {
  it("estimates, asks before forcing past the cost limit, then polls until done", async () => {
    const starts: boolean[] = [];
    server.use(...indexHandlers(["running", "succeeded"], starts));
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    await openIndexTab(user);
    expect(
      await screen.findByText(/Re-index needed: the embedding model changed/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Estimate" }));
    expect(await screen.findByText("$1.50")).toBeInTheDocument();
    expect(screen.getByText("google (gemini/gemini-embedding-001)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start indexing" }));

    const guard = await screen.findByRole("dialog", { name: "Index above the cost limit?" });
    expect(guard).toHaveTextContent("$1.00");
    await user.click(within(guard).getByRole("button", { name: "Index anyway" }));
    expect(starts).toEqual([false, true]);

    expect(await screen.findByText("Run running")).toBeInTheDocument();
    expect(await screen.findByText("Run succeeded", {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("cancels a running job", async () => {
    const starts: boolean[] = [];
    const cancelled = vi.fn();
    server.use(
      ...indexHandlers(["running"], starts),
      http.post(`${API}/api/v1/index-runs/r1/cancel`, () => {
        cancelled();
        return HttpResponse.json(run("running", { cancel_requested_at: "2026-11-18T10:01:00Z" }));
      }),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    await openIndexTab(user);
    await user.click(await screen.findByRole("button", { name: "Estimate" }));
    await user.click(await screen.findByRole("button", { name: "Start indexing" }));
    await user.click(await screen.findByRole("button", { name: "Index anyway" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(cancelled).toHaveBeenCalled();
    expect(await screen.findByText("stopping")).toBeInTheDocument();
  });
});

const task = (id: string, title: string, deps: string[] = []): MemoryItem => ({
  id,
  project_id: PROJECT_ID,
  kind: "task",
  title,
  body: "",
  status: "todo",
  priority: null,
  why: null,
  alternatives: null,
  decided_at: null,
  superseded_by_id: null,
  supersedes_ids: [],
  depends_on_ids: deps,
  is_blocked: deps.length > 0,
  source: "user",
  created_at: "2026-11-18T10:00:00Z",
  updated_at: "2026-11-18T10:00:00Z",
});

describe("memory panel", () => {
  it("checks the title locally and shows backend field errors under the field", async () => {
    let posts = 0;
    server.use(
      http.post(`${API}/api/v1/projects/${PROJECT_ID}/memory`, () => {
        posts += 1;
        return HttpResponse.json(
          {
            error: {
              code: "validation_error",
              message: "Invalid request.",
              details: {
                errors: [
                  {
                    loc: ["body", "title"],
                    msg: "Value error, must be a single line",
                    type: "value_error",
                  },
                ],
              },
            },
          },
          { status: 422 },
        );
      }),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    const panel = within(
      await screen.findByRole("complementary", { name: "Memory, index and context" }),
    );
    await user.click(await panel.findByRole("button", { name: "Add decision" }));
    await user.click(panel.getByRole("button", { name: "Save" }));
    expect(await panel.findByText("must not be empty or only whitespace")).toBeInTheDocument();
    expect(posts).toBe(0);

    const title = panel.getByLabelText("Title");
    await user.type(title, "Use PostgreSQL");
    await user.click(panel.getByRole("button", { name: "Save" }));
    const error = await panel.findByText("must be a single line");
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title.getAttribute("aria-describedby")).toContain(error.closest("p")?.id ?? "missing");
    expect(title).toHaveValue("Use PostgreSQL"); // input kept after the error
  });

  it("shows a dependency cycle next to the dependency field", async () => {
    server.use(
      http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, ({ request }) => {
        const kind = new URL(request.url).searchParams.get("kind");
        const items =
          kind === "task" ? [task("t1", "Write API", ["t2"]), task("t2", "Design schema")] : [];
        return HttpResponse.json({ items, total: items.length, limit: 100, offset: 0 });
      }),
      http.post(`${API}/api/v1/memory/t2/dependencies`, () =>
        HttpResponse.json(apiError("dependency_cycle", "That dependency would make a cycle."), {
          status: 409,
        }),
      ),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    await user.click(await screen.findByRole("button", { name: "Tasks" }));
    expect(await screen.findByText("blocked", { selector: "span" })).toBeInTheDocument();
    const card = (await screen.findByRole("heading", { name: "Design schema" })).closest("article");
    if (!card) throw new Error("no card");
    const select = within(card).getByLabelText("Depends on");
    await user.selectOptions(select, "t1");
    await user.click(within(card).getByRole("button", { name: "Add" }));
    expect(
      await within(card).findByText("That dependency would make a cycle."),
    ).toBeInTheDocument();
    expect(select).toHaveAttribute("aria-invalid", "true");
  });
});

describe("project settings", () => {
  it("warns when the default model has no saved key", async () => {
    server.use(
      http.get(`${API}/api/v1/providers`, () =>
        HttpResponse.json([
          {
            id: "google",
            name: "Google",
            supports_chat: true,
            supports_embeddings: true,
            has_key: true,
          },
          {
            id: "openai",
            name: "OpenAI",
            supports_chat: true,
            supports_embeddings: true,
            has_key: false,
          },
        ]),
      ),
      http.get(`${API}/api/v1/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...project, default_model_id: MODEL_BIG }),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}`);
    expect(await screen.findByText(/Warning: no openai key is saved/)).toBeInTheDocument();
  });
});
