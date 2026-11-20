import { describe, expect, it } from "vitest";

import { ApiError } from "../../lib/api/errors";
import { plan } from "../../test/workflowFixtures";
import {
  approveBody,
  approveErrors,
  danglingDependencies,
  initialState,
  reducer,
} from "./approvalState";

describe("approval state", () => {
  it("sends only changed, trimmed fields of chosen items", () => {
    const p = plan(3);
    let state = initialState(p);
    state = reducer(state, { type: "toggle", kind: "decision", index: 0 });
    state = reducer(state, { type: "editTask", index: 1, field: "title", value: " Task 1 " });
    state = reducer(state, { type: "editTask", index: 2, field: "priority", value: "high" });
    expect(approveBody(p, state)).toEqual({
      all: false,
      tasks: [{ index: 0 }, { index: 1 }, { index: 2, priority: "high" }],
      decisions: [],
    });
    state = reducer(state, { type: "undoEdit", kind: "task", index: 2 });
    state = reducer(state, { type: "toggle", kind: "decision", index: 0 });
    expect(approveBody(p, state)).toEqual({ all: true, tasks: [], decisions: [] });
  });

  it("finds chosen tasks that depend on left-out ones", () => {
    const p = plan(3);
    const state = reducer(initialState(p), { type: "toggle", kind: "task", index: 0 });
    expect(danglingDependencies(p, state)).toEqual([{ task: 1, dependsOn: 0 }]);
  });

  it("maps a request validation error by position back to the plan index", () => {
    const sent = { all: false, tasks: [{ index: 0 }, { index: 2, title: "x" }], decisions: [] };
    const error = new ApiError(422, "validation_error", "Invalid request.", {
      errors: [
        { loc: ["body", "tasks", 1, "title"], msg: "String should have at most 200 characters" },
      ],
    });
    const found = approveErrors(error, sent);
    expect(found.items["task:2"]?.fields.title).toBe("String should have at most 200 characters");
    expect(found.form).toBe("Fix the marked fields, then approve again.");
  });

  it("names a decision's stored body field after the proposal's 'what'", () => {
    const error = new ApiError(422, "invalid_draft", "bad", {
      kind: "decision",
      index: 0,
      errors: [{ field: "body", message: "must be at most 5000 characters" }],
    });
    expect(approveErrors(error, null).items["decision:0"]?.fields.what).toBe(
      "must be at most 5000 characters",
    );
  });
});
