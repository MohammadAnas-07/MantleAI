import { NotebookPen, Plus } from "lucide-react";
import { useState } from "react";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useMemory } from "../../hooks/queries";
import type { MemoryKind } from "../../lib/api/types";
import { MemoryForm } from "./MemoryForm";
import { MemoryItemCard } from "./MemoryItemCard";

const KINDS: { id: MemoryKind; label: string }[] = [
  { id: "requirement", label: "Requirements" },
  { id: "decision", label: "Decisions" },
  { id: "task", label: "Tasks" },
];

/** Requirements, decisions and tasks of the project. Every model sees them as pinned items. */
export function MemoryPanel({ projectId }: { projectId: string }) {
  const [kind, setKind] = useState<MemoryKind>("decision");
  const [adding, setAdding] = useState(false);
  const memory = useMemory(projectId, kind);
  const items = memory.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div
        role="group"
        aria-label="Memory kind"
        className="inline-flex flex-wrap gap-0.5 rounded-sm border border-field p-0.5"
      >
        {KINDS.map((k) => (
          <button
            key={k.id}
            type="button"
            aria-pressed={k.id === kind}
            onClick={() => {
              setKind(k.id);
              setAdding(false);
            }}
            className={`h-7 rounded-sm px-2.5 text-base transition-colors duration-150 ease-out ${k.id === kind ? "bg-hover text-text" : "font-normal text-muted hover:text-text"}`}
          >
            {k.label}
          </button>
        ))}
      </div>

      {adding ? (
        <MemoryForm
          key={kind}
          projectId={projectId}
          kind={kind}
          onDone={() => {
            setAdding(false);
          }}
        />
      ) : (
        <Button
          size="sm"
          icon={<Plus aria-hidden className="size-4" />}
          onClick={() => {
            setAdding(true);
          }}
        >
          Add {kind}
        </Button>
      )}

      {memory.isLoading ? <Skeleton label="Loading memory" /> : null}
      {memory.isError ? (
        <QueryError
          error={memory.error}
          onRetry={() => void memory.refetch()}
          retrying={memory.isFetching}
        />
      ) : null}
      {memory.data && items.length === 0 ? (
        <EmptyState icon={NotebookPen}>
          No {kind}s yet. Every model you chat with sees the project&apos;s {kind}s.
        </EmptyState>
      ) : null}
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id}>
            <MemoryItemCard item={item} siblings={items} projectId={projectId} />
          </li>
        ))}
      </ul>
      {memory.data && memory.data.total > items.length ? (
        <p className="text-sm text-muted">
          Showing {items.length} of {memory.data.total}. Older items are not listed here.
        </p>
      ) : null}
    </div>
  );
}
