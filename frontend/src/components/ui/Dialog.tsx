import { X } from "lucide-react";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "./Button";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface DialogProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/**
 * A modal dialog: focus moves inside on open, Tab stays inside, Escape closes, and focus goes
 * back to the element that opened it.
 */
export function Dialog({ title, open, onClose, children }: DialogProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    return () => {
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open]);

  if (!open) return null;

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = items[0];
    const last = items.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-sm border-2 border-dashed border-line bg-surface p-4 shadow-xl"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id={titleId} className="text-lg">
            {title}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Close"
            onClick={onClose}
            icon={<X className="size-4" aria-hidden />}
          />
        </div>
        {children}
      </div>
    </div>
  );
}

interface ConfirmProps {
  title: string;
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  children: ReactNode;
}

export function ConfirmDialog({
  title,
  open,
  onCancel,
  onConfirm,
  confirmLabel,
  danger = false,
  busy = false,
  error,
  children,
}: ConfirmProps) {
  return (
    <Dialog title={title} open={open} onClose={onCancel}>
      <div className="space-y-3 text-sm">{children}</div>
      {error ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} busy={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
