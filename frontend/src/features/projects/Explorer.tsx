import { FolderPlus, MessageSquarePlus, MessagesSquare, Folder, Workflow } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";

import { QueryError } from "../../components/QueryError";
import { Button } from "../../components/ui/Button";
import { EmptyState, Skeleton } from "../../components/ui/Feedback";
import { useConversations, useProjects } from "../../hooks/queries";
import { NewConversationDialog } from "../conversations/NewConversationDialog";
import { NewProjectDialog } from "./NewProjectDialog";

// The current page is a hover-grey row with an accent bar, never a solid fill (design-app.md).
const ROW =
  "flex h-8 items-center gap-2 truncate rounded-sm px-2 text-base no-underline transition-colors duration-150 ease-out";
const linkClass = ({ isActive }: { isActive: boolean }, inside = false) =>
  `${ROW} ${
    isActive
      ? "bg-hover font-medium text-text shadow-[inset_2px_0_0_var(--accent)]"
      : inside
        ? "font-medium text-text hover:bg-hover"
        : "text-text-2 hover:bg-hover hover:text-text"
  }`;

function GroupHeader({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-1 flex h-7 items-center justify-between pl-2">
      <h3 className="eyebrow">{title}</h3>
      {children}
    </div>
  );
}

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
    <div className="space-y-5">
      <div>
        <GroupHeader title="Projects">
          <Button
            size="sm"
            variant="ghost"
            aria-label="New project"
            onClick={() => {
              setCreating(true);
            }}
            icon={<FolderPlus aria-hidden className="size-4" />}
          />
        </GroupHeader>
        {projects.isLoading ? <Skeleton label="Loading projects" /> : null}
        {projects.isError ? (
          <QueryError
            error={projects.error}
            onRetry={() => void projects.refetch()}
            retrying={projects.isFetching}
          />
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
            No projects yet. A project points Mantle at one folder of code.
          </EmptyState>
        ) : null}
        <ul className="space-y-0.5">
          {projects.data?.map((p) => (
            <li key={p.id}>
              <NavLink
                to={`/projects/${p.id}`}
                end
                dir="auto"
                // Inside the project (a conversation, the workflow) its row stays marked.
                className={(state) => linkClass(state, p.id === projectId)}
              >
                <Folder aria-hidden className="size-4 shrink-0 text-muted" />
                <span className="truncate">{p.name}</span>
              </NavLink>
              {p.id === projectId ? (
                <ul className="mt-0.5 ml-4 space-y-0.5 border-l border-line pl-2">
                  <li>
                    <NavLink to={`/projects/${projectId}/workflow`} className={linkClass}>
                      <Workflow aria-hidden className="size-4 shrink-0 text-muted" />
                      <span className="truncate">Workflow and agents</span>
                    </NavLink>
                  </li>
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
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
      <GroupHeader title="Conversations">
        <Button
          size="sm"
          variant="ghost"
          aria-label="New conversation"
          onClick={() => {
            setCreating(true);
          }}
          icon={<MessageSquarePlus aria-hidden className="size-4" />}
        />
      </GroupHeader>
      {conversations.isLoading ? <Skeleton lines={2} label="Loading conversations" /> : null}
      {conversations.isError ? (
        <QueryError
          error={conversations.error}
          onRetry={() => void conversations.refetch()}
          retrying={conversations.isFetching}
        />
      ) : null}
      {conversations.data?.length === 0 ? (
        <EmptyState
          icon={MessagesSquare}
          action={
            <Button
              size="sm"
              onClick={() => {
                setCreating(true);
              }}
            >
              New conversation
            </Button>
          }
        >
          No conversations in this project yet.
        </EmptyState>
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
