import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type Kind = "info" | "warning" | "danger" | "success";

const BANNER: Record<Kind, { box: string; strong: string; Icon: LucideIcon; word: string }> = {
  info: { box: "bg-accent-soft", strong: "text-accent", Icon: Info, word: "Note" },
  warning: { box: "bg-warning-soft", strong: "text-warning", Icon: TriangleAlert, word: "Warning" },
  danger: { box: "bg-danger-soft", strong: "text-danger", Icon: CircleAlert, word: "Error" },
  success: { box: "bg-success-soft", strong: "text-success", Icon: CircleCheck, word: "Done" },
};

/** A notice across its column. The kind is said in words too, never by colour alone. */
export function Banner({
  kind,
  children,
  action,
}: {
  kind: Kind;
  children: ReactNode;
  action?: ReactNode;
}) {
  const { box, strong, Icon, word } = BANNER[kind];
  return (
    <div
      role={kind === "danger" || kind === "warning" ? "alert" : "status"}
      className={`flex flex-wrap items-start gap-x-2 gap-y-1 rounded-lg px-3 py-2 text-base text-text ${box}`}
    >
      <span className={`flex shrink-0 items-center gap-1.5 font-medium ${strong}`}>
        <Icon aria-hidden className="size-4 shrink-0" />
        {word}:
      </span>
      <div className="min-w-0 flex-1 break-words">{children}</div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  );
}

/** Why the list is empty and, at most, one thing to do about it. */
export function EmptyState({
  icon: Icon,
  children,
  action,
}: {
  icon: LucideIcon;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg bg-sunken px-4 py-6 text-center text-base text-muted">
      <Icon aria-hidden className="size-5" />
      <div className="max-w-prose">{children}</div>
      {action}
    </div>
  );
}

/** Grey bars with a gentle pulse; reduced motion turns the pulse off (index.css). */
export function Skeleton({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2 py-1">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-3.5 animate-pulse rounded-sm bg-hover"
          style={{ width: `${90 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

const BADGE: Record<Kind | "neutral", string> = {
  neutral: "border-field text-text-2",
  info: "border-transparent bg-accent-soft text-accent",
  warning: "border-transparent bg-warning-soft text-warning",
  danger: "border-transparent bg-danger-soft text-danger",
  success: "border-transparent bg-success-soft text-success",
};

/** A short status word, with an optional icon. Never colour alone. */
export function Badge({
  kind = "neutral",
  children,
}: {
  kind?: Kind | "neutral";
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex h-5 shrink-0 items-center gap-1 rounded-sm border px-1.5 text-xs font-medium whitespace-nowrap ${BADGE[kind]}`}
    >
      {children}
    </span>
  );
}
