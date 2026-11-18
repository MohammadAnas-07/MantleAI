// Date helpers for due dates, in the user's local time zone.

export function formatDueDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// A task is overdue when its due date is before the start of today.
export function isOverdue(iso: string | null, now: Date = new Date()): boolean {
  if (!iso) return false;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return new Date(iso) < startOfToday;
}
