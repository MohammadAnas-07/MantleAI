// HTTP client for the Taskboard API.

const BASE_URL = "http://localhost:8000";
const MAX_RETRIES = 3;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Fetch JSON, retrying network failures and 503 responses with exponential backoff.
export async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  let delay = 250;
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(BASE_URL + path, init);
      if (response.status === 503 && attempt < MAX_RETRIES) {
        await sleep(delay);
        delay *= 2;
        continue;
      }
      if (!response.ok) {
        throw new ApiError(response.status, await response.text());
      }
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError || attempt >= MAX_RETRIES) throw error;
      await sleep(delay);
      delay *= 2;
    }
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
