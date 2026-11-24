import { useParams } from "react-router";

import { QueryError } from "../../components/QueryError";
import { Skeleton } from "../../components/ui/Feedback";
import { PageHeader } from "../../components/ui/PageHeader";
import { useMemory, useMemoryItem } from "../../hooks/queries";
import type { MemoryItem, MemoryKind } from "../../lib/api/types";
import { MemoryItemCard } from "./MemoryItemCard";

/** One memory item in the workspace: where references from agent runs and the gap finder go. */
export function MemoryItemRoute() {
  const { projectId = "", itemId = "" } = useParams();
  return <MemoryItemPage key={itemId} projectId={projectId} itemId={itemId} />;
}

function MemoryItemPage({ projectId, itemId }: { projectId: string; itemId: string }) {
  const item = useMemoryItem(itemId);
  if (item.isLoading) return <Skeleton label="Loading the memory item" />;
  if (item.isError) {
    return (
      <QueryError
        error={item.error}
        onRetry={() => void item.refetch()}
        retrying={item.isFetching}
      />
    );
  }
  if (!item.data) return null;
  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader
        title={`Memory ${item.data.kind}`}
        description="One item of the project memory. Every model you chat with sees it."
      />
      <WithSiblings item={item.data} projectId={projectId} />
    </div>
  );
}

function WithSiblings({ item, projectId }: { item: MemoryItem; projectId: string }) {
  // The card shows dependency and supersede titles from the item's own kind.
  const siblings = useMemory(projectId, item.kind as MemoryKind);
  return (
    <MemoryItemCard item={item} siblings={siblings.data?.items ?? [item]} projectId={projectId} />
  );
}
