// Which links from untrusted text (model output, memory, retrieved code) may be followed.

const ALLOWED = new Set(["http:", "https:", "mailto:"]);

/**
 * The URL if it is an absolute http, https or mailto address, else null. Relative addresses
 * are refused too: in model output they would point at the app or the local API.
 */
export function safeLinkHref(raw: string | undefined): string | null {
  if (!raw) return null;
  const value = raw.trim();
  // Only absolute URLs with a scheme; URL() would resolve "/x" or "x" against a base.
  if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) return null;
  try {
    const url = new URL(value);
    return ALLOWED.has(url.protocol) ? value : null;
  } catch {
    return null;
  }
}

/** The address as shown to the user: no scheme for web links, the full value otherwise. */
export function displayTarget(href: string): string {
  return href.replace(/^https?:\/\//i, "").replace(/\/$/, "");
}
