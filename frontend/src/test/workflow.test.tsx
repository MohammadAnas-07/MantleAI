import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API, apiError, PROJECT_ID } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";
import { event, workflow } from "./workflowFixtures";

const URL = `${API}/api/v1/projects/${PROJECT_ID}/workflow`;
const PAGE = `/projects/${PROJECT_ID}/workflow`;

/** Record each POST body to a workflow action and answer with `answer`. */
function onPost(action: string, answer: () => Response) {
  const bodies: unknown[] = [];
  server.use(
    http.post(`${URL}/${action}`, async ({ request }) => {
      bodies.push(await request.json());
      return answer();
    }),
  );
  return bodies;
}

describe("workflow stages", () => {
  it("highlights the current stage and lists exactly what the gate is missing", async () => {
    renderApp(PAGE);
    // The first render of this file loads the whole workflow page and takes about 1.2 s on its
    // own, past the 1 s default; under a full parallel run it timed out.
    const bar = await screen.findByRole(
      "navigation",
      { name: "Workflow stages" },
      { timeout: 5_000 },
    );
    const current = within(bar).getByRole("button", { current: "step" });
    expect(current).toHaveTextContent("1. Requirements");
    expect(current).toHaveTextContent("(current)");
    expect(within(bar).getAllByRole("button")).toHaveLength(5);

    expect(screen.getByText("The goal of Requirements.")).toBeInTheDocument();
    expect(screen.getByText(/Gate not met:/)).toBeInTheDocument();
    const unmet = screen.getByRole("list", { name: "Unmet" });
    expect(
      within(unmet)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([
      "Goal of Requirements is written down. (checklist)",
      "At least 1 approved requirement. (have 0, need 1)",
    ]);
    // Without the gate there is no plain approve, only the override.
    expect(screen.queryByRole("button", { name: "Approve stage" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve anyway…" })).toBeInTheDocument();
  });

  it("approves a ready stage and always sends the stage the user looks at", async () => {
    server.use(http.get(URL, () => HttpResponse.json(workflow(0, { ready: true }))));
    const bodies = onPost("approve", () => HttpResponse.json(workflow(1)));
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve stage" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ stage_id: "requirements" }]);
    });
    const bar = screen.getByRole("navigation", { name: "Workflow stages" });
    expect(await within(bar).findByRole("button", { current: "step" })).toHaveTextContent(
      "2. Architecture",
    );
  });

  it("ticks and unticks checklist items, required and optional", async () => {
    const bodies = onPost("checklist", () => HttpResponse.json(workflow(0)));
    const { user } = renderApp(PAGE);
    const required = await screen.findByRole("checkbox", { name: /Goal of Requirements/ });
    expect(required).not.toBeChecked();
    expect(required.closest("li")).toHaveTextContent("(required)");
    await user.click(required);
    await user.click(screen.getByRole("checkbox", { name: /Extras of Requirements/ }));
    await waitFor(() => {
      expect(bodies).toEqual([
        { stage_id: "requirements", item_id: "goal", done: true },
        { stage_id: "requirements", item_id: "extra", done: true },
      ]);
    });
  });

  it("needs a trimmed reason to skip and shows the length", async () => {
    const bodies = onPost("skip", () => HttpResponse.json(workflow(1)));
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Skip stage…" }));
    const dialog = screen.getByRole("dialog", { name: 'Skip "Requirements"?' });
    await user.click(within(dialog).getByRole("button", { name: "Skip stage" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("A reason is required.");
    await user.type(within(dialog).getByLabelText("Reason"), "   ");
    await user.click(within(dialog).getByRole("button", { name: "Skip stage" }));
    expect(bodies).toEqual([]);

    const reason = within(dialog).getByLabelText("Reason");
    expect(reason).toHaveAttribute("maxlength", "500");
    await user.clear(reason);
    await user.type(reason, "  covered by the old spec  ");
    expect(within(dialog).getByText(/23 of 500 characters/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Skip stage" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ stage_id: "requirements", reason: "covered by the old spec" }]);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reopens an earlier stage with a reason", async () => {
    server.use(http.get(URL, () => HttpResponse.json(workflow(2))));
    const bodies = onPost("reopen", () => HttpResponse.json(workflow(0)));
    const { user } = renderApp(PAGE);
    const bar = await screen.findByRole("navigation", { name: "Workflow stages" });
    // The current stage can't be reopened; an earlier one can.
    expect(screen.queryByRole("button", { name: "Reopen this stage…" })).not.toBeInTheDocument();
    await user.click(within(bar).getByRole("button", { name: /1\. Requirements/ }));
    await user.click(screen.getByRole("button", { name: "Reopen this stage…" }));
    const dialog = screen.getByRole("dialog", { name: 'Reopen "Requirements"?' });
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));
    expect(bodies).toEqual([]);
    await user.type(within(dialog).getByLabelText("Reason"), "missed a user group");
    await user.click(within(dialog).getByRole("button", { name: "Reopen" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ stage_id: "requirements", reason: "missed a user group" }]);
    });
  });

  it("forces an approval past an unmet gate with a reason", async () => {
    const bodies = onPost("approve", () => HttpResponse.json(workflow(1)));
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve anyway…" }));
    const dialog = screen.getByRole("dialog", { name: /without its gate/ });
    expect(within(dialog).getByText(/At least 1 approved requirement/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Reason"), "demo deadline");
    await user.click(within(dialog).getByRole("button", { name: "Approve anyway" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ stage_id: "requirements", force: true, reason: "demo deadline" }]);
    });
  });

  it("reloads and explains when another tab moved the workflow first", async () => {
    let gets = 0;
    server.use(
      http.get(URL, () => {
        gets += 1;
        return HttpResponse.json(gets === 1 ? workflow(0, { ready: true }) : workflow(1));
      }),
    );
    onPost("approve", () =>
      HttpResponse.json(apiError("workflow_changed", "The current stage is now 'architecture'."), {
        status: 409,
      }),
    );
    const { user } = renderApp(PAGE);
    await user.click(await screen.findByRole("button", { name: "Approve stage" }));
    expect(await screen.findByText(/changed somewhere else/)).toBeInTheDocument();
    const bar = screen.getByRole("navigation", { name: "Workflow stages" });
    expect(await within(bar).findByRole("button", { current: "step" })).toHaveTextContent(
      "2. Architecture",
    );
    expect(gets).toBe(2);
  });

  it("offers a reset with a confirm when the stored stage no longer exists", async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json(
          apiError("unknown_stage", "The workflow is at stage 'design', which no longer exists.", {
            reset_path: `/api/v1/projects/${PROJECT_ID}/workflow/reset`,
          }),
          { status: 409 },
        ),
      ),
    );
    const bodies = onPost("reset", () => HttpResponse.json(workflow(0)));
    const { user } = renderApp(PAGE);
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset workflow…" }));
    const dialog = screen.getByRole("dialog", { name: "Reset the workflow?" });
    expect(within(dialog).getByLabelText("Reason")).toHaveFocus();
    await user.type(within(dialog).getByLabelText("Reason"), "stages changed");
    await user.click(within(dialog).getByRole("button", { name: "Reset" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ reason: "stages changed" }]);
    });
    expect(await screen.findByRole("navigation", { name: "Workflow stages" })).toBeInTheDocument();
  });

  it("lists the history newest first with who, what, reason and time", async () => {
    const events = [
      event("created", { stage_id: null }),
      event("tick", { item_id: "goal" }),
      event("approve", {
        forced: true,
        reason: "demo deadline",
        created_at: "2026-11-20T11:00:00Z",
      }),
    ];
    server.use(http.get(URL, () => HttpResponse.json(workflow(1, { events }))));
    renderApp(PAGE);
    const history = await screen.findByRole("list", { name: "Workflow history" });
    const rows = within(history).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent(/user approved "Requirements"/);
    expect(rows[0]).toHaveTextContent("forced");
    expect(rows[0]).toHaveTextContent("Reason: demo deadline");
    expect(within(rows[0] as HTMLElement).getByText(/2026/)).toHaveAttribute(
      "datetime",
      "2026-11-20T11:00:00Z",
    );
    expect(rows[1]).toHaveTextContent(/ticked "Requirements": Goal of Requirements/);
    expect(rows[2]).toHaveTextContent("started the workflow");
  });

  it("shows a retry banner when the API can't be reached", async () => {
    server.use(http.get(URL, () => HttpResponse.error()));
    const spy = vi.fn();
    const { user } = renderApp(PAGE);
    expect(await screen.findByText("Can't reach the Mantle API.")).toBeInTheDocument();
    server.use(
      http.get(URL, () => {
        spy();
        return HttpResponse.json(workflow(0));
      }),
    );
    const banner = screen.getByText("Can't reach the Mantle API.").closest("[role=alert]");
    await user.click(within(banner as HTMLElement).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("navigation", { name: "Workflow stages" })).toBeInTheDocument();
    expect(spy).toHaveBeenCalled();
  });
});

describe("long workflow history", () => {
  it("says how many old events the API left out", async () => {
    const events = Array.from({ length: 100 }, (_, i) =>
      event(i % 2 ? "untick" : "tick", { item_id: "goal", id: `e${String(i)}` }),
    );
    server.use(
      http.get(URL, () => HttpResponse.json({ ...workflow(0, { events }), events_total: 140 })),
    );
    const { user } = renderApp(PAGE);
    const history = await screen.findByRole("list", { name: "Workflow history" });
    expect(within(history).getAllByRole("listitem")).toHaveLength(20);
    await user.click(screen.getByRole("button", { name: "Show the latest 100" }));
    expect(within(history).getAllByRole("listitem")).toHaveLength(100);
    expect(screen.getByText("The 40 oldest of 140 events are not shown.")).toBeInTheDocument();
  });
});
