// The one fetch wrapper. JSON in, JSON out, errors as ApiError, a timeout, and abort support.
// It never logs request or response bodies: they can hold API keys and message text.

import { ApiError, CLIENT_CODES, errorFromBody } from "./errors";

const DEFAULT_TIMEOUT_MS = 30_000;

export function apiBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  return (fromEnv ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: Method;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  /** 0 turns the timeout off (streams). */
  timeoutMs?: number;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(apiBaseUrl() + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }
  return url.toString();
}

/**
 * Send a request and return the raw Response once its status is OK. Used directly for
 * streams; `apiFetch` adds JSON parsing.
 */
export async function apiRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const { method = "GET", body, query, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const timeout = new AbortController();
  const timer =
    timeoutMs > 0
      ? setTimeout(() => {
          timeout.abort();
        }, timeoutMs)
      : undefined;
  const signals = signal ? [signal, timeout.signal] : [timeout.signal];
  const headers: Record<string, string> = { Accept: "application/json" };
  // The backend refuses writes without a JSON content type (it forces a CORS preflight), so
  // every write sends a body, at least {}.
  const hasBody = method !== "GET" && method !== "DELETE";
  if (hasBody) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: hasBody ? JSON.stringify(body ?? {}) : undefined,
      signal: AbortSignal.any(signals),
    });
  } catch {
    if (signal?.aborted) throw new ApiError(0, CLIENT_CODES.aborted, "The request was stopped.");
    if (timeout.signal.aborted) {
      throw new ApiError(0, CLIENT_CODES.timeout, "The Mantle API took too long to answer.");
    }
    // fetch rejects with a TypeError when the server can't be reached; its text varies by
    // browser and is not useful to show.
    throw new ApiError(0, CLIENT_CODES.network, "Can't reach the Mantle API.");
  } finally {
    // For a stream the caller's signal keeps working; only the connect timeout ends here.
    if (timer !== undefined) clearTimeout(timer);
  }

  if (!response.ok) {
    const parsed: unknown = await response.json().catch(() => null);
    throw errorFromBody(response.status, parsed);
  }
  return response;
}

/** JSON request. A 204 resolves to undefined. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiRequest(path, options);
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      response.status,
      CLIENT_CODES.badResponse,
      "The API sent an unreadable answer.",
    );
  }
}
