import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useId, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { Tape } from "../components/ui/Feedback";

type Side = "left" | "right" | "bottom";

interface PanelProps {
  title: string;
  side: Side;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
  tape?: boolean;
}

const ICONS = {
  left: [ChevronLeft, ChevronRight],
  right: [ChevronRight, ChevronLeft],
  bottom: [ChevronDown, ChevronUp],
} as const;

/** A collapsible panel with a dashed border. The toggle says its state with aria-expanded. */
export function Panel({ title, side, collapsed, onToggle, children, tape = false }: PanelProps) {
  const bodyId = useId();
  const [OpenIcon, ClosedIcon] = ICONS[side];
  const Icon = collapsed ? ClosedIcon : OpenIcon;
  return (
    <section
      aria-label={title}
      className="flex min-h-0 min-w-0 flex-col rounded-sm border-2 border-dashed border-line bg-surface"
    >
      <div className="flex items-center gap-2 border-b-2 border-dashed border-line px-2 py-1">
        <h2 className="truncate text-sm">{title}</h2>
        {tape ? <Tape /> : null}
        <button
          type="button"
          className="ml-auto rounded-sm p-1 text-muted hover:text-text"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          aria-label={collapsed ? `Show ${title}` : `Hide ${title}`}
          onClick={onToggle}
        >
          <Icon aria-hidden className="size-4" />
        </button>
      </div>
      <div id={bodyId} hidden={collapsed} className="min-h-0 flex-1 overflow-auto p-2">
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
      className="w-1.5 cursor-col-resize rounded-sm hover:bg-line/40 focus-visible:bg-accent"
    />
  );
}
