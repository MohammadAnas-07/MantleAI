import { NotebookPen } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { Banner, EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useMemory } from "../../hooks/queries";
import { errorMessage } from "../../lib/api/errors";
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
      <div role="group" aria-label="Memory kind" className="flex flex-wrap gap-1">
        {KINDS.map((k) => (
          <Button
            key={k.id}
            size="sm"
            variant={k.id === kind ? "primary" : "secondary"}
            aria-pressed={k.id === kind}
            onClick={() => {
              setKind(k.id);
              setAdding(false);
            }}
          >
            {k.label}
          </Button>
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
          variant="primary"
          size="sm"
          onClick={() => {
            setAdding(true);
          }}
        >
          Add {kind}
        </Button>
      )}

      {memory.isLoading ? <Skeleton label="Loading memory" /> : null}
      {memory.isError ? <Banner kind="danger">{errorMessage(memory.error)}</Banner> : null}
      {memory.data && items.length === 0 ? (
        <EmptyState icon={NotebookPen}>No {kind}s yet. They are sent to every model.</EmptyState>
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
          Showing {items.length} of {memory.data.total}.
        </p>
      ) : null}
    </div>
  );
}
