// Our own words for model-call failures that need a "what to do". Provider messages are never
// shown: they can echo a prompt. Other codes keep the backend's message, which is ours too.

const TEXT: Record<string, string> = {
  credential_unreadable:
    "The saved API key can't be decrypted with the current MASTER_ENCRYPTION_KEY (it changed). Restore the previous master key in backend/.env, or enter the key again in Settings.",
  no_credential: "There is no API key for this model's provider. Add one in Settings.",
  auth_failed: "The provider refused the API key. Check or replace it in Settings.",
  provider_unavailable:
    "The provider did not answer (it may be down, overloaded or too slow). Nothing more was sent; try again later.",
  internal_error:
    "The API hit an internal error. The text so far is saved; the API log has the error type.",
};

export const KEYS_UNREADABLE =
  "Saved API keys can't be decrypted with the current MASTER_ENCRYPTION_KEY. Restore the previous master key in backend/.env, or enter your keys again in Settings.";

/** A clear message for a failure code; `fallback` (the backend's message) for other codes. */
export function llmErrorText(code: string | null | undefined, fallback?: string): string {
  return (code ? TEXT[code] : undefined) ?? fallback ?? "The call failed.";
}

/** True when the code has its own message here. */
export function hasLlmErrorText(code: string | null | undefined): boolean {
  return Boolean(code && code in TEXT);
}
