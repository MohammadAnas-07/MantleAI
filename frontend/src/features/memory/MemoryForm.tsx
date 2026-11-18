import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type SubmitEvent } from "react";

import { Button } from "../../components/ui/Button";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/ui/Field";
import { keys } from "../../hooks/queries";
import { api } from "../../lib/api/endpoints";
import { errorMessage, fieldErrors } from "../../lib/api/errors";
import type { MemoryKind } from "../../lib/api/types";
import { limits, memoryRules, validateMemory } from "../../lib/limits";

export function MemoryForm({
  projectId,
  kind,
  onDone,
}: {
  projectId: string;
  kind: MemoryKind;
  onDone: () => void;
}) {
  const client = useQueryClient();
  const rules = memoryRules[kind];
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [why, setWhy] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  const create = useMutation({
    mutationFn: () =>
      api.createMemory(projectId, {
        kind,
        title: title.trim(),
        body: body.trim() || null,
        status: status || null,
        priority: priority || null,
        ...(kind === "decision" ? { why: why.trim() || null } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.memory(projectId, kind) });
      onDone();
    },
  });

  // Server errors keep the input: nothing is cleared until the item is saved.
  const errors = { ...fieldErrors(create.error), ...clientErrors };
  const known = new Set(["title", "body", "why", "status", "priority"]);
  const formError =
    create.error && !Object.keys(fieldErrors(create.error)).some((f) => known.has(f))
      ? errorMessage(create.error)
      : null;

  const submit = (event: SubmitEvent) => {
    event.preventDefault();
    const found = validateMemory({ title, body, why });
    setClientErrors(found);
    if (Object.keys(found).length === 0) create.mutate();
  };

  return (
    <form
      onSubmit={submit}
      noValidate
      className="space-y-2 rounded-sm border-2 border-dashed border-line p-2"
    >
      <TextInput
        label="Title"
        value={title}
        maxLength={limits.memoryTitle}
        onChange={(e) => {
          setTitle(e.target.value);
        }}
        error={errors.title}
        dir="auto"
      />
      <TextArea
        label={kind === "decision" ? "What was decided" : "Details (optional)"}
        value={body}
        maxLength={limits.memoryText}
        onChange={(e) => {
          setBody(e.target.value);
        }}
        error={errors.body}
      />
      {kind === "decision" ? (
        <TextArea
          label="Why (optional)"
          value={why}
          maxLength={limits.memoryText}
          onChange={(e) => {
            setWhy(e.target.value);
          }}
          error={errors.why}
        />
      ) : null}
      <div className="grid grid-cols-2 gap-2">
        <SelectInput
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
          }}
          error={errors.status}
        >
          <option value="">Default</option>
          {rules.statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </SelectInput>
        {rules.priorities.length > 0 ? (
          <SelectInput
            label="Priority"
            value={priority}
            onChange={(e) => {
              setPriority(e.target.value);
            }}
            error={errors.priority}
          >
            <option value="">None</option>
            {rules.priorities.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </SelectInput>
        ) : null}
      </div>
      <FormError message={formError} />
      <div className="flex justify-end gap-2">
        <Button onClick={onDone}>Cancel</Button>
        <Button type="submit" variant="primary" busy={create.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}
