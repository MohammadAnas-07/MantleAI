import { useState, type ReactNode, type SubmitEvent } from "react";

import { errorMessage, fieldErrors } from "../lib/api/errors";
import { limits } from "../lib/limits";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { FormError, TextArea } from "./ui/Field";

interface ReasonDialogProps {
  title: string;
  open: boolean;
  onCancel: () => void;
  /** Called with the trimmed reason; never with an empty one. */
  onSubmit: (reason: string) => void;
  confirmLabel: string;
  label?: string;
  danger?: boolean;
  busy?: boolean;
  /** The last request's error: a reason problem shows under the field, the rest above. */
  error?: unknown;
  max?: number;
  children?: ReactNode;
}

/**
 * Asks for a required reason before an action the backend logs with one (skip, reopen, force,
 * reset, reject). The reason is trimmed, and its length is checked like the backend does.
 */
export function ReasonDialog({
  title,
  open,
  onCancel,
  onSubmit,
  confirmLabel,
  label = "Reason",
  danger = false,
  busy = false,
  error,
  max = limits.workflowReason,
  children,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const trimmed = reason.trim();
  const serverFieldError = fieldErrors(error).reason;
  const formError = error && !serverFieldError ? errorMessage(error) : null;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    if (!trimmed) {
      setLocalError("A reason is required.");
      return;
    }
    if (trimmed.length > max) {
      setLocalError(`The reason can be at most ${max} characters.`);
      return;
    }
    setLocalError(null);
    onSubmit(trimmed);
  };

  const close = () => {
    setReason("");
    setLocalError(null);
    onCancel();
  };

  return (
    <Dialog title={title} open={open} onClose={close}>
      <form onSubmit={submit} noValidate className="space-y-3 text-base">
        {children}
        <TextArea
          label={label}
          value={reason}
          maxLength={max}
          required
          data-autofocus
          onChange={(e) => {
            setReason(e.target.value);
            setLocalError(null);
          }}
          error={localError ?? serverFieldError}
          help={`Required. ${trimmed.length} of ${max} characters.`}
        />
        <FormError message={formError} />
        <div className="flex justify-end gap-2">
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" variant={danger ? "danger" : "primary"} busy={busy}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
