import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { FormError, TextArea, TextInput } from "../../components/ui/Field";
import { api } from "../../lib/api/endpoints";
import { errorMessage, fieldErrors } from "../../lib/api/errors";
import type { MemoryItem } from "../../lib/api/types";
import { limits, validateMemory } from "../../lib/limits";

/** Replace a decision with a new one or an existing one. */
export function SupersedeDialog({
  item,
  siblings,
  onClose,
  onDone,
}: {
  item: MemoryItem;
  siblings: MemoryItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const selectId = useId();
  const [byId, setById] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [why, setWhy] = useState("");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const run = useMutation({
    mutationFn: () =>
      api.supersede(
        item.id,
        byId
          ? { by_id: byId }
          : {
              decision: {
                title: title.trim(),
                ...(body.trim() ? { body: body.trim() } : {}),
                ...(why.trim() ? { why: why.trim() } : {}),
              },
            },
      ),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  const others = siblings.filter((s) => s.id !== item.id && s.status !== "superseded");
  const errors = { ...fieldErrors(run.error), ...clientErrors };

  const submit = () => {
    if (!byId) {
      const found = validateMemory({ title, body, why });
      setClientErrors(found);
      if (Object.keys(found).length > 0) return;
    }
    run.mutate();
  };

  return (
    <Dialog title="Supersede decision" open onClose={onClose}>
      <div className="space-y-3 text-sm">
        <p dir="auto">&ldquo;{item.title}&rdquo; will be marked superseded.</p>
        <div className="flex flex-col gap-1">
          <label htmlFor={selectId}>Replace with an existing decision</label>
          <select
            id={selectId}
            value={byId}
            onChange={(e) => {
              setById(e.target.value);
            }}
            className="rounded-sm border border-field bg-paper px-2 py-1.5"
          >
            <option value="">No: write a new decision below</option>
            {others.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
              </option>
            ))}
          </select>
        </div>
        {!byId ? (
          <>
            <TextInput
              label="New decision"
              value={title}
              maxLength={limits.memoryTitle}
              onChange={(e) => {
                setTitle(e.target.value);
              }}
              error={errors.title}
              dir="auto"
            />
            <TextArea
              label="What was decided"
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
              }}
              error={errors.body}
            />
            <TextArea
              label="Why"
              value={why}
              onChange={(e) => {
                setWhy(e.target.value);
              }}
              error={errors.why}
            />
          </>
        ) : null}
        <FormError message={run.isError && !errors.title ? errorMessage(run.error) : null} />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={run.isPending} onClick={submit}>
            Supersede
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
