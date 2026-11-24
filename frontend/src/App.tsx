import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router";

import { PageHeader } from "./components/ui/PageHeader";

import { ConversationRoute } from "./features/conversations/ConversationView";
import { MemoryItemRoute } from "./features/memory/MemoryItemPage";
import { HomePage } from "./features/projects/HomePage";
import { ProjectRoute } from "./features/projects/ProjectPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { WorkflowRoute } from "./features/workflow/WorkflowPage";
import { AppShell } from "./layout/AppShell";
import { makeQueryClient } from "./lib/queryClient";

export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/projects/:projectId" element={<ProjectRoute />} />
        <Route path="/projects/:projectId/c/:conversationId" element={<ConversationRoute />} />
        <Route path="/projects/:projectId/workflow" element={<WorkflowRoute />} />
        <Route path="/projects/:projectId/memory/:itemId" element={<MemoryItemRoute />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  );
}

function NotFound() {
  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader title="Page not found" />
      <p className="text-base">
        This address doesn&apos;t match a page. <Link to="/">Go to the start page</Link>.
      </p>
    </div>
  );
}

export function App() {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
