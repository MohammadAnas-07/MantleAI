import { FolderOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/Feedback";
import { NewProjectDialog } from "./NewProjectDialog";

export function HomePage() {
  const [creating, setCreating] = useState(false);
  return (
    <div className="mx-auto max-w-xl space-y-4 pt-8">
      <h1 className="text-xl">Mantle</h1>
      <EmptyState
        icon={FolderOpen}
        action={
          <Button
            variant="primary"
            onClick={() => {
              setCreating(true);
            }}
          >
            New project
          </Button>
        }
      >
        Pick a project in the explorer, or create one. Add a provider key in Settings first.
      </EmptyState>
      <NewProjectDialog
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
      />
    </div>
  );
}
