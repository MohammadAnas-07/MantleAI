import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useId, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

type Side = "left" | "right" | "bottom";

interface PanelProps {
  title: string;
  side: Side;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
  /** Classes for the panel's own surface (the sidebar is sunken, the rest paper). */
  className?: string;
}

const ICONS = {
  left: [ChevronLeft, ChevronRight],
  right: [ChevronRight, ChevronLeft],
  bottom: [ChevronDown, ChevronUp],
} as const;

/** A collapsible column or bar. The toggle says its state with aria-expanded. */
export function Panel({ title, side, collapsed, onToggle, children, className = "" }: PanelProps) {
  const bodyId = useId();
  const [OpenIcon, ClosedIcon] = ICONS[side];
  const Icon = collapsed ? ClosedIcon : OpenIcon;
  return (
    <section aria-label={title} className={`flex min-h-0 min-w-0 flex-1 flex-col ${className}`}>
      <div className="flex h-9 shrink-0 items-center gap-2 px-3">
        <h2 className="truncate text-sm text-muted">{title}</h2>
        <button
          type="button"
          className="ml-auto inline-flex size-7 items-center justify-center rounded-sm text-muted transition-colors duration-150 ease-out hover:bg-hover hover:text-text"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          aria-label={collapsed ? `Show ${title}` : `Hide ${title}`}
          onClick={onToggle}
        >
          <Icon aria-hidden className="size-4" />
        </button>
      </div>
      <div id={bodyId} hidden={collapsed} className="min-h-0 flex-1 overflow-auto px-3 pb-3">
        {children}
      </div>
    </section>
  );
}

/** A keyboard-reachable resize handle between columns: arrow keys change the width. */
export function ResizeHandle({
  label,
  value,
  onChange,
  min,
  max,
  invert = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  invert?: boolean;
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.shiftKey ? 64 : 16;
    const sign = invert ? -1 : 1;
    if (event.key === "ArrowRight") onChange(clamp(value + step * sign));
    else if (event.key === "ArrowLeft") onChange(clamp(value - step * sign));
    else return;
    event.preventDefault();
  };
  const onPointerDown = (event: PointerEvent) => {
    const startX = event.clientX;
    const start = value;
    const move = (e: globalThis.PointerEvent) => {
      const delta = (e.clientX - startX) * (invert ? -1 : 1);
      onChange(clamp(start + delta));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      className="relative w-px shrink-0 cursor-col-resize bg-line outline-offset-0 before:absolute before:inset-y-0 before:-right-1 before:-left-1 before:content-[''] hover:bg-field focus-visible:bg-accent"
    />
  );
}
