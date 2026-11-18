// One error type for everything the API client can fail with. The backend always answers
// errors as {"error": {"code", "message", "details"}}; network problems, timeouts and aborts
// get their own codes so the UI can tell them apart.

export type ErrorDetails = Record<string, unknown>;

export const CLIENT_CODES = {
  network: "network_error",
  timeout: "timeout",
  aborted: "aborted",
  badResponse: "bad_response",
} as const;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetails;

  constructor(status: number, code: string, message: string, details: ErrorDetails = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** The backend could not be reached at all (not an error it answered with). */
  get isNetwork(): boolean {
    return this.code === CLIENT_CODES.network;
  }

  get isAbort(): boolean {
    return this.code === CLIENT_CODES.aborted;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Turn a parsed error body into an ApiError. Unknown shapes still give a readable message. */
export function errorFromBody(status: number, body: unknown): ApiError {
  if (isRecord(body) && isRecord(body.error)) {
    const { code, message, details } = body.error;
    return new ApiError(
      status,
      typeof code === "string" ? code : "http_error",
      typeof message === "string" ? message : `Request failed (${status}).`,
      isRecord(details) ? details : {},
    );
  }
  return new ApiError(status, "http_error", `Request failed (${status}).`);
}

/** Field-level messages from a 422 validation error: {"name": "String should have..."}. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const out: Record<string, string> = {};
  const list = error.details.errors;
  if (Array.isArray(list)) {
    for (const item of list) {
      if (!isRecord(item) || !Array.isArray(item.loc)) continue;
      // loc is ["body", "field", ...]; the last string part names the field.
      const parts = item.loc.filter((p): p is string => typeof p === "string" && p !== "body");
      const field = parts.at(-1);
      if (field && typeof item.msg === "string" && !(field in out)) {
        out[field] = item.msg.replace(/^Value error, /, "");
      }
    }
  }
  const field = error.details.field;
  if (typeof field === "string" && !(field in out)) out[field] = error.message;
  return out;
}

/** A short message for the UI; never includes request content. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong.";
}
