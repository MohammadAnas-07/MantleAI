import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { ProjectProfile } from "../lib/api/types";
import { API, apiError, CONV_A, PROJECT_ID, preview } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

const URL = `${API}/api/v1/projects/${PROJECT_ID}/profile`;

const profile = (extra: Partial<ProjectProfile> = {}): ProjectProfile => ({
  project_id: PROJECT_ID,
  built: true,
  built_at: "2026-11-21T10:00:00Z",
  index_run_id: "r1",
  out_of_date: false,
  out_of_date_reasons: [],
  languages: [
    { name: "python", files: 60, share: 0.6 },
    { name: "tsx", files: 40, share: 0.4 },
  ],
  frameworks: [{ name: "FastAPI", source: "backend/pyproject.toml" }],
  commands: [
    {
      name: "npm run test",
      command: "vitest run",
      source: "frontend/package.json",
      kind: "script",
    },
    { name: "pytest", command: "pytest", source: "backend/pyproject.toml", kind: "inferred" },
  ],
  markers: [{ name: "migrations", source: "backend/alembic/env.py" }],
  manifests: [{ kind: "pyproject", source: "backend/pyproject.toml" }],
  dependencies: [
    { name: "fastapi", ecosystem: "python", dev: false, source: "backend/pyproject.toml" },
    { name: "pytest", ecosystem: "python", dev: true, source: "backend/pyproject.toml" },
  ],
  entry_points: [{ source: "backend/app/main.py", kind: "python" }],
  layout: [{ path: "backend", files: 60 }],
  ...extra,
});

async function openProfile(body: ProjectProfile | ReturnType<typeof apiError>, status = 200) {
  server.use(http.get(URL, () => HttpResponse.json(body, { status })));
  const view = renderApp(`/projects/${PROJECT_ID}`);
  await view.user.click(await screen.findByRole("tab", { name: "Profile" }));
  return view;
}

describe("project profile panel", () => {
  it("shows every fact with the file it came from", async () => {
    await openProfile(profile());
    expect(await screen.findByText(/Built .* from the files, no model/)).toBeInTheDocument();
    expect(screen.getByText("python 60% · 60")).toBeInTheDocument();
    const frameworks = screen.getByRole("region", { name: "Frameworks" });
    expect(within(frameworks).getByText("FastAPI")).toBeInTheDocument();
    expect(within(frameworks).getByText("backend/pyproject.toml")).toBeInTheDocument();
    const commands = screen.getByRole("region", { name: "Commands" });
    expect(within(commands).getByText("npm run test: vitest run")).toBeInTheDocument();
    expect(within(commands).getByText("inferred")).toBeInTheDocument();
    const deps = screen.getByRole("region", { name: "Dependencies" });
    expect(within(deps).getByText("pytest (dev)")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Folders" })).toHaveTextContent("60 files");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explains an empty profile", async () => {
    await openProfile(
      profile({ built: false, built_at: null, index_run_id: null, languages: [], commands: [] }),
    );
    expect(await screen.findByText(/No profile yet/)).toBeInTheDocument();
    expect(screen.getByText(/Index the project in the Index tab/)).toBeInTheDocument();
  });

  it("says when the profile may be out of date, and why", async () => {
    await openProfile(
      profile({ out_of_date: true, out_of_date_reasons: ["source_changed", "index_changed"] }),
    );
    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent("may be out of date");
    expect(note).toHaveTextContent("the project folder changed since it was built");
    expect(note).toHaveTextContent("a later index run ended without rebuilding it");
  });

  it("shows the error when the profile can't be read", async () => {
    await openProfile(apiError("not_found", "Project not found."), 404);
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found.");
  });

  it("shows repository text as text, never as HTML", async () => {
    const hostile = '<img src=x onerror="alert(1)"> [click](javascript:alert(1))';
    await openProfile(
      profile({
        commands: [{ name: hostile, command: "x", source: "package.json", kind: "script" }],
      }),
    );
    expect(await screen.findByText(`${hostile}: x`)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.queryByRole("link", { name: /click/ })).not.toBeInTheDocument();
  });

  it("is reached with the keyboard", async () => {
    server.use(http.get(URL, () => HttpResponse.json(profile())));
    const { user } = renderApp(`/projects/${PROJECT_ID}`);
    const memory = await screen.findByRole("tab", { name: "Memory" });
    memory.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Profile" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("region", { name: "Frameworks" })).toBeInTheDocument();
  });
});

describe("context panel", () => {
  it("names the profile section and lists profile fields left out", async () => {
    const report = preview("m1");
    server.use(
      http.get(`${API}/api/v1/conversations/${CONV_A}/handoff-preview`, () =>
        HttpResponse.json({
          ...report,
          sections: [
            ...report.sections,
            {
              name: "project_profile",
              included: true,
              tokens: 80,
              items_total: 8,
              items_included: 6,
              content: "",
            },
          ],
          dropped: ["profile layout", "profile entry_points"],
          profile: {
            tokens: 80,
            max_tokens: 600,
            fields: ["languages"],
            dropped: [
              { field: "layout", reason: "profile_budget" },
              { field: "entry_points", reason: "profile_budget" },
            ],
          },
        }),
      ),
    );
    const { user } = renderApp(`/projects/${PROJECT_ID}/c/${CONV_A}`);
    await user.click(await screen.findByRole("tab", { name: "Context" }));
    expect(await screen.findByText("Project profile")).toBeInTheDocument();
    expect(screen.getByText("6/8")).toBeInTheDocument();
    expect(
      screen.getByText(/Project profile fields left out: layout, entry_points \(profile_budget\)/),
    ).toBeInTheDocument();
  });
});
