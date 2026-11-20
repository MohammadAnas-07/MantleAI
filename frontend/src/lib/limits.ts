// Client-side limits that match the backend's validation (schemas and app/core/config.py), so
// most mistakes are caught before a request. The backend still checks everything.

export const limits = {
  projectName: 200,
  projectDescription: 5000,
  path: 4096,
  conversationTitle: 300,
  message: 200_000,
  memoryTitle: 200,
  memoryText: 5000,
  credentialLabel: 100,
  apiKeyMin: 8,
  apiKeyMax: 500,
  // WORKFLOW_REASON_MAX_LENGTH and AGENT_REQUIREMENT_MAX_CHARS (app/core/config.py)
  workflowReason: 500,
  requirementText: 4000,
} as const;

/** Memory statuses and priorities per kind (backend: projects/memory_service.py). */
export const memoryRules = {
  decision: {
    statuses: ["proposed", "accepted", "rejected", "deprecated"],
    priorities: [] as string[],
  },
  requirement: {
    statuses: ["draft", "approved", "dropped"],
    priorities: ["must", "should", "could"],
  },
  task: {
    statuses: ["todo", "in_progress", "done", "blocked"],
    priorities: ["high", "medium", "low"],
  },
} as const;

/** Checks the same limits as the backend, so most mistakes don't need a request. */
export function validateMemory(values: {
  title: string;
  body: string;
  why: string;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  const title = values.title.trim();
  if (!title) errors.title = "must not be empty or only whitespace";
  else if (title.includes("\n")) errors.title = "must be a single line";
  else if (title.length > limits.memoryTitle)
    errors.title = `must be at most ${limits.memoryTitle} characters`;
  for (const field of ["body", "why"] as const) {
    if (values[field].trim().length > limits.memoryText) {
      errors[field] = `must be at most ${limits.memoryText} characters`;
    }
  }
  return errors;
}
