import { screen, waitFor, within } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { AGENT_RUN_POLL_MS } from "../hooks/queries";
import type { AgentRun } from "../lib/api/types";
import { API, apiError, MODEL_BIG, MODEL_SMALL, PROJECT_ID, project } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";
import {
  agentRun,
  memoryItem,
  PROJECT_B,
  REQ_ID,
  RUN_ID,
  TASK_ID,
  waitingRun,
} from "./workflowFixtures";

const RUNS = `${API}/api/v1/projects/${PROJECT_ID}/agent-runs`;
const RUN = `${API}/api/v1/agent-runs/${RUN_ID}`;
const PAGE = `/projects/${PROJECT_ID}/workflow`;

const estimate = (extra = {}) => ({
  steps: 2,
  input_tokens: 2000,
  output_tokens: 8000,
  cost_usd: "0.018",
  cost_limit_usd: "0.50",
  model: "google/Small Model",
  over_limit: false,
  ...extra,
});

function withRequirement() {
  server.use(
    http.get(`${API}/api/v1/projects/${PROJECT_ID}/memory`, ({ request }) => {
      const kind = new URL(request.url).searchParams.get("kind");
      const items =
        kind === "requirement"
          ? [memoryItem(REQ_ID, "requirement", "Users can log in")]
          : kind === "task"
            ? [memoryItem(TASK_ID, "task", "Existing login task")]
            : [];
      return HttpResponse.json({ items, total: items.length, limit: 100, offset: 0 });
    }),
  );
}

/** The run list and the run itself answer with `run`. */
function showRun(run: AgentRun | (() => AgentRun)) {
  const get = typeof run === "function" ? run : () => run;
  server.use(
    http.get(RUNS, () => HttpResponse.json({ items: [get()] })),
    http.get(RUN, () => HttpResponse.json(get())),
  );
}

function recordPost(url: string, answer: (body: unknown, n: number) => Response) {
  const bodies: unknown[] = [];
  server.use(
    http.post(url, async ({ request }) => {
      const body = await request.json();
      bodies.push(body);
      return answer(body, bodies.length);
    }),
  );
  return bodies;
}

/** Wait for the approval list; role queries over a long plan are slow in jsdom. */
async function openApproval() {
  await screen.findByText("Planner draft", {}, { timeout: 5_000 });
}

async function fillPlanForm(user: ReturnType<typeof renderApp>["user"]) {
  const requirement = await screen.findByLabelText("Requirement from memory");
  await waitFor(() => {
    expect(within(requirement).getAllByRole("option")).toHaveLength(2);
  });
  await user.selectOptions(requirement, REQ_ID);
  const model = screen.getByLabelText("Run model");
  await waitFor(() => {
    expect(model).toHaveValue(MODEL_SMALL);
  });
}

describe("agent run start", () => {
  it("shows the estimate first and starts only on confirm", async () => {
    withRequirement();
    const estimates = recordPost(`${RUNS}/estimate`, () => HttpResponse.json(estimate()));
    const starts = recordPost(RUNS, () => HttpResponse.json(agentRun("queued"), { status: 202 }));
    server.use(http.get(RUN, () => HttpResponse.json(agentRun("running"))));
    const { user } = renderApp(PAGE);
    await fillPlanForm(user);
    expect(screen.getByRole("checkbox", { name: "Use code context" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Estimate cost" }));
    expect(await screen.findByText("$0.02")).toBeInTheDocument();
    expect(starts).toEqual([]);
    const sent = {
      run_type: "plan",
      model_id: MODEL_SMALL,
      use_code_context: false,
      force: false,
      requirement_id: REQ_ID,
    };
    expect(estimates).toEqual([sent]);

    await user.click(screen.getByRole("button", { name: "Confirm and start" }));
    await waitFor(() => {
      expect(starts).toEqual([sent]);
    });
    const view = await screen.findByRole("article", { name: "Agent run" });
    expect(await within(view).findByText("running")).toBeInTheDocument();
    expect(within(view).getByText("The Planner is drafting.")).toBeInTheDocument();
  });

  it("drops the estimate when an input changes", async () => {
    withRequirement();
    recordPost(`${RUNS}/estimate`, () => HttpResponse.json(estimate()));
    const { user } = renderApp(PAGE);
    await fillPlanForm(user);
    await user.click(screen.getByRole("button", { name: "Estimate cost" }));
    expect(await screen.findByRole("button", { name: "Confirm and start" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Use code context" }));
    expect(screen.queryByRole("button", { name: "Confirm and start" })).not.toBeInTheDocument();
  });

  it("asks again with the numbers when the backend's cost guard answers 409", async () => {
    withRequirement();
    recordPost(`${RUNS}/estimate`, () => HttpResponse.json(estimate()));
    const starts = recordPost(RUNS, (body) =>
      (body as { force: boolean }).force
        ? HttpResponse.json(agentRun("queued"), { status: 202 })
        : HttpResponse.json(
            apiError("cost_limit_exceeded", "Over.", {
              estimate: { ...estimate(), cost_usd: "0.81" },
            }),
            { status: 409 },
          ),
    );
    server.use(http.get(RUN, () => HttpResponse.json(agentRun("queued"))));
    const { user } = renderApp(PAGE);
    await fillPlanForm(user);
    await user.click(screen.getByRole("button", { name: "Estimate cost" }));
    await user.click(await screen.findByRole("button", { name: "Confirm and start" }));
    const dialog = await screen.findByRole("dialog", { name: "Run above the cost limit?" });
    expect(dialog).toHaveTextContent("$0.81");
    expect(dialog).toHaveTextContent("$0.50");
    await user.click(within(dialog).getByRole("button", { name: "Run anyway" }));
    await waitFor(() => {
      expect(starts.map((b) => (b as { force: boolean }).force)).toEqual([false, true]);
    });
  });

  it("explains a model without a price", async () => {
    withRequirement();
    recordPost(`${RUNS}/estimate`, () => HttpResponse.json(estimate({ cost_usd: null })));
    recordPost(RUNS, () =>
      HttpResponse.json(apiError("model_not_priced", "no price"), { status: 422 }),
    );
    const { user } = renderApp(PAGE);
    await fillPlanForm(user);
    await user.click(screen.getByRole("button", { name: "Estimate cost" }));
    expect(await screen.findByText(/no price in the catalog/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm and start" }));
    expect(await screen.findByText(/AGENT_ALLOW_UNPRICED_MODELS=true/)).toBeInTheDocument();
  });

  it("shows the other tab's run when a second start gets 409", async () => {
    withRequirement();
    let listed: AgentRun[] = [];
    server.use(
      http.get(RUNS, () => HttpResponse.json({ items: listed })),
      http.get(RUN, () => HttpResponse.json(agentRun("running"))),
    );
    recordPost(`${RUNS}/estimate`, () => HttpResponse.json(estimate()));
    recordPost(RUNS, () => {
      listed = [agentRun("running")];
      return HttpResponse.json(apiError("agent_run_in_progress", "busy"), { status: 409 });
    });
    const { user } = renderApp(PAGE);
    await fillPlanForm(user);
    await user.click(screen.getByRole("button", { name: "Estimate cost" }));
    await user.click(await screen.findByRole("button", { name: "Confirm and start" }));
    expect(await screen.findByRole("article", { name: "Agent run" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Estimate cost" })).not.toBeInTheDocument();
    expect(screen.getByText(/Only one runs at a time/)).toBeInTheDocument();
  });
});

describe("agent run status", () => {
  it("polls while the run is active and stops at the end", async () => {
    let gets = 0;
    showRun(() => {
      gets += 1;
      return gets < 2 ? agentRun("running") : agentRun("completed", { run_type: "review" });
    });
    renderApp(PAGE);
    const view = await screen.findByRole("article", { name: "Agent run" });
    expect(await within(view).findByText("completed", {}, { timeout: 5_000 })).toBeInTheDocument();
    const after = gets;
    await new Promise((resolve) => setTimeout(resolve, AGENT_RUN_POLL_MS * 2));
    expect(gets).toBe(after);
  }, 15_000);

  it("cancels a running run", async () => {
    showRun(agentRun("running"));
    const cancels = recordPost(`${RUN}/cancel`, () => HttpResponse.json(agentRun("cancelled")));
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Cancel run" }));
    await waitFor(() => {
      expect(cancels).toEqual([{}]);
    });
    expect(await screen.findByText("cancelled")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  });

  it("shows the real final status when the cancel came too late", async () => {
    let finished = false;
    showRun(() => (finished ? agentRun("completed", { run_type: "review" }) : agentRun("running")));
    recordPost(`${RUN}/cancel`, () => {
      finished = true;
      return HttpResponse.json(apiError("agent_run_not_active", "done"), { status: 409 });
    });
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Cancel run" }));
    expect(await screen.findByText(/already ended before the cancel/)).toBeInTheDocument();
    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(screen.queryByText("cancelled")).not.toBeInTheDocument();
  });

  it.each([
    [
      "invalid_output",
      "tasks.0 depends on itself.",
      /also after one retry.*tasks\.0 depends on itself/,
    ],
    ["quota_exhausted", "raw quota text", /quota for this key is used up/],
    ["provider_unavailable", "raw provider text 503", /did not answer.*Try again later/],
    ["step_timeout", null, /longer than the time limit/],
    ["interrupted", "raw interrupted text", /server stopped while this run/],
  ])("explains a %s failure in its own words", async (code, message, expected) => {
    showRun(agentRun("failed", { error: code, error_message: message }));
    renderApp(`${PAGE}?run=${RUN_ID}`);
    expect(await screen.findByText(expected)).toBeInTheDocument();
    if (message && code !== "invalid_output") {
      expect(document.body).not.toHaveTextContent(message);
    }
  });

  it("offers the suggested models after a context error and puts one in the form", async () => {
    showRun(
      agentRun("failed", {
        error: "context_too_long",
        error_details: {
          suggested_models: [
            {
              model_id: MODEL_BIG,
              display_name: "Big Model",
              provider: "openai",
              context_window: 1_000_000,
            },
          ],
        },
      }),
    );
    const { user } = renderApp(`${PAGE}?run=${RUN_ID}`);
    expect(await screen.findByText(/too long for this model/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Use Big Model/ }));
    expect(screen.getByLabelText("Run model")).toHaveValue(MODEL_BIG);
  });

  it("never shows a stale poll from the previous project", async () => {
    const other = { ...project, id: PROJECT_B, name: "Other project" };
    let answer: (() => void) | null = null;
    server.use(
      http.get(`${API}/api/v1/projects`, () => HttpResponse.json([project, other])),
      http.get(`${API}/api/v1/projects/${PROJECT_B}`, () => HttpResponse.json(other)),
      http.get(`${API}/api/v1/projects/${PROJECT_B}/memory`, () =>
        HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 }),
      ),
      http.get(`${API}/api/v1/projects/${PROJECT_B}/conversations`, () => HttpResponse.json([])),
      http.get(RUNS, () => HttpResponse.json({ items: [agentRun("running")] })),
      http.get(RUN, async () => {
        await new Promise<void>((resolve) => {
          answer = resolve;
        });
        return HttpResponse.json(waitingRun());
      }),
    );
    const { user } = renderApp(PAGE);
    await waitFor(() => {
      expect(answer).not.toBeNull();
    });
    await user.click(screen.getByRole("link", { name: "Other project" }));
    await user.click(await screen.findByRole("link", { name: /Workflow and agents/ }));
    expect(
      await screen.findByRole("heading", { name: "Workflow: Other project" }),
    ).toBeInTheDocument();
    (answer as (() => void) | null)?.();
    await delay(50);
    expect(screen.queryByRole("article", { name: "Agent run" })).not.toBeInTheDocument();
    expect(screen.queryByText("Planner draft")).not.toBeInTheDocument();
    expect(await screen.findByText("No agent runs yet.")).toBeInTheDocument();
  });
});

describe("approval view", () => {
  it("opens a run waiting for approval on page load, next to the review", async () => {
    showRun(waitingRun());
    renderApp(PAGE);
    expect(await screen.findByText("Planner draft")).toBeInTheDocument();
    expect(screen.getByText("verdict: changes requested")).toBeInTheDocument();
    expect(screen.getByText("Task 1 has no rate limit.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "proposed task: Task 1" })).toHaveAttribute(
      "href",
      "#plan-task-1",
    );
    expect(screen.getByText("Users have email")).toBeInTheDocument();
    expect(screen.getByText("Do we need SSO?")).toBeInTheDocument();
    expect(screen.getByText("4 of 4 selected")).toBeInTheDocument();
  });

  it("approves everything unchanged with all=true", async () => {
    showRun(waitingRun());
    const bodies = recordPost(`${RUN}/approve`, () =>
      HttpResponse.json({
        run: agentRun("approved"),
        task_ids: [],
        decision_ids: [],
        warnings: [],
      }),
    );
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve selected…" }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ all: true, tasks: [], decisions: [] }]);
    });
  });

  it("sends a subset with edits, and links what was created", async () => {
    withRequirement();
    let decided = false;
    showRun(() => (decided ? agentRun("approved", { saved_item_ids: [TASK_ID] }) : waitingRun()));
    const bodies = recordPost(`${RUN}/approve`, () => {
      decided = true;
      return HttpResponse.json({
        run: agentRun("approved", { saved_item_ids: [TASK_ID] }),
        task_ids: [TASK_ID],
        decision_ids: [],
        warnings: [{ code: "dependency_not_saved", task: 2, depends_on: 1 }],
      });
    });
    const { user } = renderApp(PAGE);
    await openApproval();
    await user.click(screen.getByRole("checkbox", { name: "Include Task 1" }));
    await user.click(screen.getByRole("checkbox", { name: "Include Use argon2" }));
    await user.click(screen.getByRole("button", { name: "Edit Task 0" }));
    const title = within(document.getElementById("plan-task-0") as HTMLElement).getByLabelText(
      "Title",
    );
    await user.clear(title);
    await user.type(title, "  Login form  ");
    expect(screen.getByText("2 of 4 selected")).toBeInTheDocument();
    // Task 2 depends on Task 1, which is left out.
    expect(screen.getByText(/“Task 2” depends on “Task 1”/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve selected…" }));
    const dialog = screen.getByRole("dialog", { name: "Save the selected items?" });
    expect(dialog).toHaveTextContent("2 tasks (as todo) and 0 decisions");
    expect(dialog).toHaveTextContent("1 dependency link");
    await user.click(within(dialog).getByRole("button", { name: "Approve and save" }));
    await waitFor(() => {
      expect(bodies).toEqual([
        { all: false, tasks: [{ index: 0, title: "Login form" }, { index: 2 }], decisions: [] },
      ]);
    });
    const created = await screen.findByRole("list", { name: "Created items" });
    expect(
      await within(created).findByRole("link", { name: "task: Existing login task" }),
    ).toHaveAttribute("href", `/projects/${PROJECT_ID}/memory/${TASK_ID}`);
    expect(
      screen.getByText(/which was not chosen, so that link was not saved/),
    ).toBeInTheDocument();
  });

  it("puts a backend validation error on the right field and keeps the selection", async () => {
    showRun(waitingRun());
    recordPost(`${RUN}/approve`, () =>
      HttpResponse.json(
        apiError("invalid_draft", "Proposed task 2 is not valid: title: must be a single line", {
          kind: "task",
          index: 2,
          errors: [{ field: "title", message: "must be a single line" }],
        }),
        { status: 422 },
      ),
    );
    const { user } = renderApp(PAGE);
    await openApproval();
    await user.click(screen.getByRole("checkbox", { name: "Include Task 1" }));
    await user.click(screen.getByRole("button", { name: "Edit Task 0" }));
    const first = within(document.getElementById("plan-task-0") as HTMLElement).getByLabelText(
      "Title",
    );
    await user.type(first, " edited");
    await user.click(screen.getByRole("button", { name: "Approve selected…" }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));

    const task2 = document.getElementById("plan-task-2") as HTMLElement;
    const field = await within(task2).findByLabelText("Title");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(within(task2).getByText("must be a single line")).toBeInTheDocument();
    expect(screen.getByText(/Fix the marked item/)).toBeInTheDocument();
    // Nothing the user chose or typed is lost.
    expect(screen.getByRole("checkbox", { name: "Include Task 1" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Include Task 0 edited" })).toBeChecked();
    expect(screen.getByText("3 of 4 selected")).toBeInTheDocument();
  });

  it("shows the reason when limits changed since the plan was made", async () => {
    showRun(waitingRun());
    recordPost(`${RUN}/approve`, () =>
      HttpResponse.json(
        apiError(
          "draft_limits_changed",
          "Proposed decision 0 no longer meets the current limits: title: too long.",
          {
            kind: "decision",
            index: 0,
          },
        ),
        { status: 422 },
      ),
    );
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve selected…" }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    const decision = document.getElementById("plan-decision-0") as HTMLElement;
    expect(
      await within(decision).findByText(/no longer meets the current limits/),
    ).toBeInTheDocument();
    expect(screen.getByText(/The limits changed since this plan was made/)).toBeInTheDocument();
    expect(screen.getByText("4 of 4 selected")).toBeInTheDocument();
  });

  it("explains a lost approval race and shows the run's real state", async () => {
    let decided = false;
    showRun(() => (decided ? agentRun("rejected", { decision_reason: "not now" }) : waitingRun()));
    recordPost(`${RUN}/approve`, () => {
      decided = true;
      return HttpResponse.json(apiError("agent_run_not_waiting", "rejected"), { status: 409 });
    });
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve selected…" }));
    await user.click(screen.getByRole("button", { name: "Approve and save" }));
    expect(
      await screen.findByText(/already approved or rejected somewhere else/),
    ).toBeInTheDocument();
    expect(await screen.findByText("not now")).toBeInTheDocument();
    expect(screen.queryByText("Planner draft")).not.toBeInTheDocument();
  });

  it("needs a reason to reject", async () => {
    showRun(waitingRun());
    const bodies = recordPost(`${RUN}/reject`, () =>
      HttpResponse.json(agentRun("rejected", { decision_reason: "too broad" })),
    );
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Reject run…" }));
    const dialog = screen.getByRole("dialog", { name: "Reject this run?" });
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));
    expect(within(dialog).getByText("A reason is required.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
    await user.type(within(dialog).getByLabelText("Reason"), " too broad ");
    await user.click(within(dialog).getByRole("button", { name: "Reject" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ reason: "too broad" }]);
    });
  });

  it("flags a possible duplicate with a link to the existing task", async () => {
    withRequirement();
    const run = waitingRun();
    const plan = run.result.plan as { tasks: { possible_duplicate_of: string | null }[] };
    if (plan.tasks[0]) plan.tasks[0].possible_duplicate_of = TASK_ID;
    showRun(run);
    renderApp(PAGE);
    await openApproval();
    const task0 = document.getElementById("plan-task-0") as HTMLElement;
    expect(within(task0).getByText("possible duplicate")).toBeInTheDocument();
    expect(
      await within(task0).findByRole("link", { name: "task: Existing login task" }),
    ).toBeInTheDocument();
  });

  it("keeps a 30-item plan usable from the keyboard", async () => {
    showRun(waitingRun(30));
    const { user } = renderApp(PAGE);
    await openApproval();
    await user.click(screen.getByRole("button", { name: "Select none" }));
    expect(screen.getByText("0 of 31 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve selected…" })).toBeDisabled();
    const box = screen.getByRole("checkbox", { name: "Include Task 29" });
    box.focus();
    await user.keyboard(" ");
    expect(box).toBeChecked();
    await user.tab();
    expect(screen.getByRole("button", { name: "Edit Task 29" })).toHaveFocus();
    expect(screen.getByText("1 of 31 selected")).toBeInTheDocument();
  });

  it("never logs plan text to the console", async () => {
    const log = vi.spyOn(console, "log");
    const error = vi.spyOn(console, "error");
    showRun(waitingRun());
    renderApp(PAGE);
    await screen.findByText("Planner draft");
    for (const spy of [log, error]) {
      expect(spy.mock.calls.flat().join(" ")).not.toContain("Task 1");
    }
  });
});

describe("run list summaries", () => {
  it("opens a waiting run from a summary that has no plan", async () => {
    const full = waitingRun();
    const summary = Object.fromEntries(
      Object.entries(full).filter(
        ([k]) => !["result", "steps", "input", "estimate", "warnings"].includes(k),
      ),
    );
    server.use(
      http.get(RUNS, () => HttpResponse.json({ items: [summary] })),
      http.get(RUN, () => HttpResponse.json(full)),
    );
    renderApp(PAGE);
    expect(await screen.findByText("Planner draft", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Agent runs" })).toHaveTextContent("waiting");
  });
});
