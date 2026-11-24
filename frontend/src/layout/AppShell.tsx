import { ChevronRight, Moon, Settings, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useMatch } from "react-router";

import { BackendBanner } from "../components/BackendBanner";
import { ActivityPanel } from "../features/activity/ActivityPanel";
import { AiPanel } from "../features/ai/AiPanel";
import { ModelSwitcher } from "../features/conversations/ModelSwitcher";
import { Explorer } from "../features/projects/Explorer";
import { useConversation, useProject } from "../hooks/queries";
import { useIsNarrow } from "../hooks/useMediaQuery";
import { useTheme } from "../hooks/useTheme";
import { Panel, ResizeHandle } from "./Panel";

const ICON_LINK =
  "inline-flex size-8 items-center justify-center rounded-sm text-muted transition-colors duration-150 ease-out hover:bg-hover hover:text-text";

/**
 * Top bar, left explorer, center workspace, right AI panel and bottom activity log
 * (docs/design-app.md). Columns touch and are split by hairlines. Under 768px everything
 * stacks in one column, navigation first.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const projectMatch = useMatch("/projects/:projectId/*");
  const conversationMatch = useMatch("/projects/:projectId/c/:conversationId");
  const projectId = projectMatch?.params.projectId;
  const conversationId = conversationMatch?.params.conversationId;
  const project = useProject(projectId);
  const [theme, toggleTheme] = useTheme();
  const narrow = useIsNarrow();

  const [leftOpen, setLeftOpen] = useState(!narrow);
  const [rightOpen, setRightOpen] = useState(!narrow);
  const [bottomOpen, setBottomOpen] = useState(false);
  const [leftWidth, setLeftWidth] = useState(240);
  const [rightWidth, setRightWidth] = useState(360);

  const left = (
    <Panel
      title="Explorer"
      side="left"
      collapsed={!leftOpen}
      onToggle={() => {
        setLeftOpen((v) => !v);
      }}
      className="bg-sunken"
    >
      <nav aria-label="Projects and conversations">
        <Explorer projectId={projectId} conversationId={conversationId} />
      </nav>
    </Panel>
  );
  const right = (
    <Panel
      title="AI panel"
      side="right"
      collapsed={!rightOpen}
      onToggle={() => {
        setRightOpen((v) => !v);
      }}
    >
      <aside aria-label="Memory, index and context" className="flex h-full min-h-0 flex-col">
        <AiPanel projectId={projectId} conversationId={conversationId} />
      </aside>
    </Panel>
  );

  return (
    <div className="flex h-full flex-col bg-paper">
      <header className="flex min-h-12 shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-sunken px-4 py-1.5">
        <Link to="/" className="font-serif text-lg text-text no-underline">
          Mantle
        </Link>
        <Breadcrumb
          projectId={projectId}
          projectName={project.data?.name}
          conversationId={conversationId}
        />
        <div className="ml-auto flex items-center gap-1">
          {conversationId && projectId ? <ModelSwitcher conversationId={conversationId} /> : null}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            className={ICON_LINK}
          >
            {theme === "dark" ? (
              <Sun aria-hidden className="size-4" />
            ) : (
              <Moon aria-hidden className="size-4" />
            )}
          </button>
          <Link to="/settings" aria-label="Settings" className={ICON_LINK}>
            <Settings aria-hidden className="size-4" />
          </Link>
        </div>
      </header>

      <BackendBanner />

      {narrow ? (
        <div className="flex flex-col">
          <div className="border-b border-line">{left}</div>
          <main className="min-h-[60vh] px-4 py-4">{children}</main>
          <div className="border-t border-line">{right}</div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <div
            style={{ width: leftOpen ? leftWidth : 140 }}
            className="flex min-h-0 shrink-0 flex-col bg-sunken"
          >
            {left}
          </div>
          {leftOpen ? (
            <ResizeHandle
              label="Resize explorer"
              value={leftWidth}
              onChange={setLeftWidth}
              min={180}
              max={480}
            />
          ) : (
            <div aria-hidden className="w-px shrink-0 bg-line" />
          )}
          <main className="min-h-0 min-w-0 flex-1 overflow-auto px-4 py-5 lg:px-6">{children}</main>
          {rightOpen ? (
            <ResizeHandle
              label="Resize AI panel"
              value={rightWidth}
              onChange={setRightWidth}
              min={260}
              max={640}
              invert
            />
          ) : (
            <div aria-hidden className="w-px shrink-0 bg-line" />
          )}
          <div
            style={{ width: rightOpen ? rightWidth : 140 }}
            className="flex min-h-0 shrink-0 flex-col"
          >
            {right}
          </div>
        </div>
      )}

      <div
        role="region"
        aria-label="Activity"
        className={`flex shrink-0 flex-col border-t border-line bg-sunken ${bottomOpen ? "max-h-64 min-h-32" : ""}`}
      >
        <Panel
          title="Activity"
          side="bottom"
          collapsed={!bottomOpen}
          onToggle={() => {
            setBottomOpen((v) => !v);
          }}
        >
          <ActivityPanel />
        </Panel>
      </div>
    </div>
  );
}

/** Where you are: the project (a link to its page) and the open conversation. */
function Breadcrumb({
  projectId,
  projectName,
  conversationId,
}: {
  projectId: string | undefined;
  projectName: string | undefined;
  conversationId: string | undefined;
}) {
  if (!projectId) {
    return (
      <span className="text-base text-muted" aria-label="Current project">
        No project selected
      </span>
    );
  }
  return (
    <div className="flex min-w-0 items-center gap-1 text-base">
      <Link
        to={`/projects/${projectId}`}
        aria-label={`Current project: ${projectName ?? "loading"}`}
        className="truncate text-text no-underline hover:underline"
        dir="auto"
      >
        {projectName ?? "…"}
      </Link>
      {conversationId ? <ConversationCrumb conversationId={conversationId} /> : null}
    </div>
  );
}

function ConversationCrumb({ conversationId }: { conversationId: string }) {
  const conversation = useConversation(conversationId);
  return (
    <>
      <ChevronRight aria-hidden className="size-4 shrink-0 text-muted" />
      <span className="truncate text-muted" dir="auto">
        {conversation.data ? conversation.data.title || "Untitled conversation" : "…"}
      </span>
    </>
  );
}
