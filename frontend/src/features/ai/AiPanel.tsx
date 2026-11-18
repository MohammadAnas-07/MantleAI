import { FolderSearch } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "../../components/ui/Feedback";
import { Tabs } from "../../components/ui/Tabs";
import { ContextPanel } from "../context/ContextPanel";
import { IndexPanel } from "../index/IndexPanel";
import { MemoryPanel } from "../memory/MemoryPanel";

type Tab = "memory" | "index" | "context";

const TABS = [
  { id: "memory" as const, label: "Memory" },
  { id: "index" as const, label: "Index" },
  { id: "context" as const, label: "Context" },
];

export function AiPanel({
  projectId,
  conversationId,
}: {
  projectId: string | undefined;
  conversationId: string | undefined;
}) {
  const [tab, setTab] = useState<Tab>("memory");
  if (!projectId) {
    return (
      <EmptyState icon={FolderSearch}>
        Open a project to see its memory, index and context.
      </EmptyState>
    );
  }
  return (
    <Tabs label="Project tools" tabs={TABS} active={tab} onChange={setTab}>
      {/* Keyed by id: a panel never shows the previous project's or conversation's data. */}
      {tab === "memory" ? <MemoryPanel key={projectId} projectId={projectId} /> : null}
      {tab === "index" ? <IndexPanel key={projectId} projectId={projectId} /> : null}
      {tab === "context" ? (
        conversationId ? (
          <ContextPanel key={conversationId} conversationId={conversationId} />
        ) : (
          <p className="text-sm text-muted">
            Open a conversation to see what would be sent to a model.
          </p>
        )
      ) : null}
    </Tabs>
  );
}
