// Login state kept in localStorage.

const STORAGE_KEY = "taskboard.session";

export interface Session {
  userId: number;
  token: string;
}

export function saveSession(session: Session): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function loadSession(): Session | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? (JSON.parse(raw) as Session) : null;
}

// Logging out removes the stored token, so the next request is anonymous.
export function logout(): void {
  localStorage.removeItem(STORAGE_KEY);
}
