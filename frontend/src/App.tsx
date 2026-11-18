import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { ConversationRoute } from "./features/conversations/ConversationView";
import { HomePage } from "./features/projects/HomePage";
import { ProjectRoute } from "./features/projects/ProjectPage";
import { SettingsPage } from "./features/settings/SettingsPage";
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
        <Route path="*" element={<p>Page not found.</p>} />
      </Routes>
    </AppShell>
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
