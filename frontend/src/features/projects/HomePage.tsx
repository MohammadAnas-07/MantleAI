import { FolderOpen } from "lucide-react";
import { useState } from "react";

import { Link } from "react-router";

import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/Feedback";
import { PageHeader } from "../../components/ui/PageHeader";
import { NewProjectDialog } from "./NewProjectDialog";

export function HomePage() {
  const [creating, setCreating] = useState(false);
  return (
    <div className="mx-auto max-w-2xl space-y-6 pt-6">
      <PageHeader
        title="Mantle"
        description="A local workspace for building software with several models. Projects keep their memory and index here, on this machine."
      />
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
        Pick a project in the explorer, or create one. To chat, add a provider key in{" "}
        <Link to="/settings">the settings</Link> first.
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
