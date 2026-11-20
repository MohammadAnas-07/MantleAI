// Words for run types, statuses and failures, shared by every agent view.

import { ApiError } from "../../lib/api/errors";
import { hasLlmErrorText, llmErrorText } from "../../lib/llmErrors";
import type { RunWarning, SuggestedModel } from "../../lib/api/types";

export const RUN_TYPE_LABEL: Record<string, string> = {
  plan: "Plan (Planner + Reviewer)",
  review: "Review (Reviewer only)",
  gap_finder: "Gap finder",
};

// Our own words for each failure. Provider messages are never shown: they can echo a prompt.
const FAILURE_TEXT: Record<string, string> = {
  invalid_output:
    "The model's answer did not match the expected format, also after one retry. Nothing was saved. Try again, or pick a stronger model.",
  step_timeout: "A step took longer than the time limit. Nothing was saved. Try again later.",
  quota_exhausted:
    "The provider's quota for this key is used up (for example a daily limit). Try again after it resets, or pick another model.",
  rate_limited:
    "The provider is rate limiting this key. Wait a minute and try again, or pick another model.",
  context_too_long:
    "The prompt is too long for this model. Pick a model with a bigger context window.",
  provider_unavailable:
    "The provider did not answer (it may be down or overloaded). Nothing was saved. Try again later.",
  auth_failed: "The provider refused the API key. Check the key in Settings.",
  no_credential: "There is no API key for this model's provider. Add one in Settings.",
  model_unavailable: "This model is not available. Pick another one.",
  interrupted: "The server stopped while this run was in progress. Start it again.",
  internal_error:
    "The run stopped on an internal error. Start it again; if it repeats, check the API log.",
  cancelled: "You cancelled this run.",
};

/** A failure explained for the user. Only our validation message is shown for invalid_output,
 * because it names fields and never quotes the model's answer. */
export function failureText(code: string, backendMessage: string | null): string {
  const text =
    FAILURE_TEXT[code] ?? (hasLlmErrorText(code) ? llmErrorText(code) : "The run failed.");
  if (code === "invalid_output" && backendMessage) return `${text} (${backendMessage})`;
  return text;
}

/** Models the backend suggests in a failed run's `error_details` or an error's `details`. */
export function suggestedModels(details: Record<string, unknown>): SuggestedModel[] {
  const list = details.suggested_models;
  return Array.isArray(list) ? (list as SuggestedModel[]) : [];
}

// Start errors come from the backend's checks before any model call, or (gap finder) from the
// call itself. Our wording for the ones that need advice; the backend's own message otherwise.
const START_TEXT: Record<string, string> = {
  model_not_priced:
    "This model has no price in the model catalog, so the cost limit can't be applied. Pick a model with prices (or set AGENT_ALLOW_UNPRICED_MODELS=true on the server).",
  agent_run_in_progress:
    "This project already has an agent run in progress (maybe started in another tab). It is shown below.",
};

const PROVIDER_CODES = new Set([
  "credential_unreadable",
  "invalid_output",
  "step_timeout",
  "quota_exhausted",
  "rate_limited",
  "context_too_long",
  "provider_unavailable",
  "auth_failed",
]);

export function startErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong.";
  const start = START_TEXT[error.code];
  if (start) return start;
  // Provider errors never show the provider's text.
  if (PROVIDER_CODES.has(error.code)) return failureText(error.code, null);
  return error.message;
}

/** A warning field as text; anything that isn't a plain string or number is not shown. */
const part = (value: unknown, fallback: string): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : fallback;

const WARNING_TEXT: Record<string, (w: RunWarning) => string> = {
  unknown_reference: (w) =>
    `A reference in ${part(w.where, "the answer")} to an item the project doesn't have was dropped.`,
  memory_trimmed: (w) =>
    `${part(w.count, "Some")} memory items did not fit in the prompt and were left out.`,
  code_context_failed: () => "Code search failed, so the run had no code context.",
  dependency_not_saved: (w) =>
    `Proposed task ${part(w.task, "?")} depends on task ${part(w.depends_on, "?")}, which was not chosen, so that link was not saved.`,
};

/** A warning in our words; the raw fields of an unknown warning are not shown. */
export function warningText(warning: RunWarning): string {
  return WARNING_TEXT[warning.code]?.(warning) ?? `Warning: ${warning.code}.`;
}
