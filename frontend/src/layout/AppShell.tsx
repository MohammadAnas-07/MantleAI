import { Moon, Settings, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useMatch } from "react-router";

import { BackendBanner } from "../components/BackendBanner";
import { ActivityPanel } from "../features/activity/ActivityPanel";
import { AiPanel } from "../features/ai/AiPanel";
import { ModelSwitcher } from "../features/conversations/ModelSwitcher";
import { Explorer } from "../features/projects/Explorer";
import { useProject } from "../hooks/queries";
import { useIsNarrow } from "../hooks/useMediaQuery";
import { useTheme } from "../hooks/useTheme";
import { Panel, ResizeHandle } from "./Panel";

/**
 * Top bar, left explorer, center workspace, right AI panel and bottom activity log
 * (docs/design-app.md). Under 768px everything stacks in one column.
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
      tape
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
    <div className="noise flex h-full flex-col gap-2 p-2">
      <header className="flex flex-wrap items-center gap-3 rounded-sm border-2 border-dashed border-line bg-surface px-3 py-2">
        <Link to="/" className="label text-lg text-text">
          Mantle
        </Link>
        <span className="truncate text-sm text-muted" aria-label="Current project">
          {projectId ? (project.data?.name ?? "…") : "No project selected"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {conversationId && projectId ? <ModelSwitcher conversationId={conversationId} /> : null}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            className="rounded-sm border-2 border-line p-1.5"
          >
            {theme === "dark" ? (
              <Sun aria-hidden className="size-4" />
            ) : (
              <Moon aria-hidden className="size-4" />
            )}
          </button>
          <Link
            to="/settings"
            aria-label="Settings"
            className="rounded-sm border-2 border-line p-1.5 text-text"
          >
            <Settings aria-hidden className="size-4" />
          </Link>
        </div>
      </header>

      <BackendBanner />

      {narrow ? (
        <div className="flex flex-col gap-2">
          <main className="min-h-[60vh] rounded-sm border-2 border-dashed border-line bg-surface p-3">
            {children}
          </main>
          {right}
          {left}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-0.5">
          <div
            style={{ width: leftOpen ? leftWidth : 140 }}
            className="flex min-h-0 shrink-0 flex-col"
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
          ) : null}
          <main className="min-h-0 min-w-0 flex-1 overflow-auto rounded-sm border-2 border-dashed border-line bg-surface p-3">
            {children}
          </main>
          {rightOpen ? (
            <ResizeHandle
              label="Resize AI panel"
              value={rightWidth}
              onChange={setRightWidth}
              min={260}
              max={640}
              invert
            />
          ) : null}
          <div
            style={{ width: rightOpen ? rightWidth : 140 }}
            className="flex min-h-0 shrink-0 flex-col"
          >
            {right}
          </div>
        </div>
      )}

      <div role="region" aria-label="Activity" className={bottomOpen ? "max-h-64 min-h-32" : ""}>
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
