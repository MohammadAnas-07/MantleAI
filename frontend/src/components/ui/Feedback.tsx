import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type Kind = "info" | "warning" | "danger" | "success";

const BANNER: Record<Kind, { className: string; Icon: LucideIcon; word: string }> = {
  info: { className: "bg-info text-on-info", Icon: Info, word: "Note" },
  warning: { className: "bg-warning text-on-warning", Icon: TriangleAlert, word: "Warning" },
  danger: { className: "bg-danger-bg text-on-danger", Icon: CircleAlert, word: "Error" },
  success: { className: "border-2 border-success text-text", Icon: CircleCheck, word: "Done" },
};

/** A full-width notice. The kind is said in words too, never by colour alone. */
export function Banner({
  kind,
  children,
  action,
}: {
  kind: Kind;
  children: ReactNode;
  action?: ReactNode;
}) {
  const { className, Icon, word } = BANNER[kind];
  return (
    <div
      role={kind === "danger" || kind === "warning" ? "alert" : "status"}
      className={`flex flex-wrap items-center gap-2 rounded-sm px-3 py-2 text-sm ${className}`}
    >
      <Icon aria-hidden className="size-4 shrink-0" />
      <span className="label">{word}:</span>
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

/** Dashed box with the noise texture, one icon, one sentence and one action. */
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
    <div className="noise relative flex flex-col items-center gap-2 rounded-sm border-2 border-dashed border-line p-6 text-center text-sm text-muted">
      <span
        aria-hidden="true"
        className="label absolute -top-2 right-4 rotate-3 bg-warning px-2 text-xs text-on-warning select-none"
      >
        EMPTY
      </span>
      <Icon aria-hidden className="size-6" />
      <div>{children}</div>
      {action}
    </div>
  );
}

/** Gentle pulse; reduced motion turns the animation off (index.css). */
export function Skeleton({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded-sm bg-line/30"
          style={{ width: `${90 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

const BADGE: Record<Kind | "neutral", string> = {
  neutral: "border-line text-text",
  info: "border-accent text-text",
  warning: "bg-warning text-on-warning border-warning",
  danger: "border-danger text-danger",
  success: "border-success text-text",
};

export function Badge({
  kind = "neutral",
  children,
}: {
  kind?: Kind | "neutral";
  children: ReactNode;
}) {
  return (
    <span
      className={`label inline-flex items-center gap-1 rounded-sm border px-1.5 text-xs ${BADGE[kind]}`}
    >
      {children}
    </span>
  );
}

/** Decoration only: a strip of "duct tape" in a panel header. Hidden from assistive tech. */
export function Tape({ text = "MANTLE" }: { text?: string }) {
  return (
    <span
      aria-hidden="true"
      className="label pointer-events-none -rotate-2 bg-warning/80 px-2 text-[10px] tracking-widest text-on-warning select-none"
    >
      {text}
    </span>
  );
}
