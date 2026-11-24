import { FolderPlus, MessageSquarePlus, MessagesSquare, Folder, Workflow } from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router";

import { Button } from "../../components/ui/Button";
import { EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useConversations, useProjects } from "../../hooks/queries";
import { errorMessage } from "../../lib/api/errors";
import { NewConversationDialog } from "../conversations/NewConversationDialog";
import { NewProjectDialog } from "./NewProjectDialog";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block truncate rounded-sm px-2 py-1 text-sm ${isActive ? "bg-primary text-on-primary" : "text-text hover:bg-hover"}`;

export function Explorer({
  projectId,
  conversationId,
}: {
  projectId: string | undefined;
  conversationId: string | undefined;
}) {
  const projects = useProjects();
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-xs text-muted">Projects</h3>
          <Button
            size="sm"
            variant="ghost"
            aria-label="New project"
            onClick={() => {
              setCreating(true);
            }}
            icon={<FolderPlus aria-hidden className="size-4" />}
          />
        </div>
        {projects.isLoading ? <Skeleton label="Loading projects" /> : null}
        {projects.isError ? (
          <p className="text-sm text-danger">{errorMessage(projects.error)}</p>
        ) : null}
        {projects.data?.length === 0 ? (
          <EmptyState
            icon={Folder}
            action={
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setCreating(true);
                }}
              >
                New project
              </Button>
            }
          >
            No projects yet.
          </EmptyState>
        ) : null}
        <ul className="space-y-0.5">
          {projects.data?.map((p) => (
            <li key={p.id}>
              <NavLink to={`/projects/${p.id}`} end className={linkClass}>
                {p.name}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
      {projectId ? (
        <NavLink to={`/projects/${projectId}/workflow`} className={linkClass}>
          <span className="inline-flex items-center gap-1.5">
            <Workflow aria-hidden className="size-4" /> Workflow and agents
          </span>
        </NavLink>
      ) : null}
      {projectId ? (
        <ConversationList key={projectId} projectId={projectId} conversationId={conversationId} />
      ) : null}
      <NewProjectDialog
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
      />
    </div>
  );
}

function ConversationList({
  projectId,
  conversationId,
}: {
  projectId: string;
  conversationId: string | undefined;
}) {
  const conversations = useConversations(projectId);
  const [creating, setCreating] = useState(false);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-xs text-muted">Conversations</h3>
        <Button
          size="sm"
          variant="ghost"
          aria-label="New conversation"
          onClick={() => {
            setCreating(true);
          }}
          icon={<MessageSquarePlus aria-hidden className="size-4" />}
        />
      </div>
      {conversations.isLoading ? <Skeleton lines={2} label="Loading conversations" /> : null}
      {conversations.isError ? (
        <p className="text-sm text-danger">{errorMessage(conversations.error)}</p>
      ) : null}
      {conversations.data?.length === 0 ? (
        <EmptyState icon={MessagesSquare}>No conversations in this project.</EmptyState>
      ) : null}
      <ul className="space-y-0.5">
        {conversations.data?.map((c) => (
          <li key={c.id}>
            <NavLink
              to={`/projects/${projectId}/c/${c.id}`}
              className={linkClass}
              aria-current={c.id === conversationId ? "page" : undefined}
              dir="auto"
            >
              {c.title || "Untitled"}
            </NavLink>
          </li>
        ))}
      </ul>
      <NewConversationDialog
        projectId={projectId}
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
      />
    </div>
  );
}
