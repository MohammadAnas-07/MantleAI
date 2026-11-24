import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "../../components/ui/Button";
import { CONTROL } from "../../components/ui/Field";
import { Badge } from "../../components/ui/Feedback";
import { api } from "../../lib/api/endpoints";
import { errorMessage } from "../../lib/api/errors";
import type { MemoryItem } from "../../lib/api/types";

/** A task's dependencies: add one from the same list, remove one, see backend refusals. */
export function Dependencies({
  item,
  siblings,
  onChange,
}: {
  item: MemoryItem;
  siblings: MemoryItem[];
  onChange: () => void;
}) {
  const selectId = useId();
  const errorId = useId();
  const [pick, setPick] = useState("");
  const add = useMutation({
    mutationFn: (dependsOn: string) => api.addDependency(item.id, dependsOn),
    onSuccess: () => {
      setPick("");
      onChange();
    },
  });
  const removeDep = useMutation({
    mutationFn: (dependsOn: string) => api.removeDependency(item.id, dependsOn),
    onSuccess: onChange,
  });
  const deps = item.depends_on_ids ?? [];
  const titles = new Map(siblings.map((s) => [s.id, s.title]));
  const candidates = siblings.filter((s) => s.id !== item.id && !deps.includes(s.id));

  return (
    <div className="space-y-2">
      {deps.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {deps.map((dep) => (
            <li key={dep}>
              <Badge>
                needs: {titles.get(dep) ?? "another task"}
                <button
                  type="button"
                  className="inline-flex size-4 items-center justify-center rounded-sm hover:bg-hover"
                  aria-label={`Remove dependency on ${titles.get(dep) ?? "task"}`}
                  onClick={() => {
                    removeDep.mutate(dep);
                  }}
                >
                  <X aria-hidden className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex items-center gap-2">
        <label htmlFor={selectId} className="text-sm font-normal text-muted">
          Depends on
        </label>
        <select
          id={selectId}
          value={pick}
          aria-invalid={add.isError}
          aria-describedby={add.isError ? errorId : undefined}
          onChange={(e) => {
            setPick(e.target.value);
          }}
          className={`${CONTROL} h-7 min-w-0 flex-1`}
        >
          <option value="">Choose a task</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          disabled={!pick}
          busy={add.isPending}
          onClick={() => {
            add.mutate(pick);
          }}
        >
          Add
        </Button>
      </div>
      {add.isError ? (
        // Cycles, self-dependencies and missing tasks come back from the backend; show them here.
        <p id={errorId} role="alert" className="text-danger">
          {errorMessage(add.error)}
        </p>
      ) : null}
      {removeDep.isError ? (
        <p role="alert" className="text-danger">
          {errorMessage(removeDep.error)}
        </p>
      ) : null}
    </div>
  );
}
