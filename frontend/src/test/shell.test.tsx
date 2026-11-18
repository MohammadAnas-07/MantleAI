import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, PROJECT_ID } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

describe("app shell", () => {
  it("shows projects in the explorer and the project page", async () => {
    renderApp(`/projects/${PROJECT_ID}`);
    const nav = await screen.findByRole("navigation", { name: "Projects and conversations" });
    expect(await within(nav).findByRole("link", { name: "Demo project" })).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Demo project", level: 1 }),
    ).toBeInTheDocument();
    expect(await within(nav).findByRole("link", { name: "First chat" })).toBeInTheDocument();
  });

  it("shows a banner with Retry when the API can't be reached", async () => {
    let up = false;
    server.use(
      http.get(`${API}/health`, () =>
        up ? HttpResponse.json({ status: "ok", database: "up" }) : HttpResponse.error(),
      ),
    );
    const { user } = renderApp("/");
    const banner = await screen.findByRole("alert", { name: "" });
    expect(banner).toHaveTextContent(/Can't reach the Mantle API at http:\/\/127\.0\.0\.1:8000/);
    up = true;
    await user.click(within(banner).getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(screen.queryByText(/Start it with/)).not.toBeInTheDocument();
    });
  });

  it("panels collapse and say so", async () => {
    const { user } = renderApp("/");
    const toggle = await screen.findByRole("button", { name: "Hide Explorer" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Show Explorer" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
