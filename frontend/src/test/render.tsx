import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "../App";

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
}

/** The whole app at `path`, with a fresh cache, as the user sees it. */
export function renderApp(path: string) {
  const client = testQueryClient();
  const user = userEvent.setup();
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, user, client };
}

export function renderWithClient(ui: ReactNode) {
  const client = testQueryClient();
  const user = userEvent.setup();
  return {
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>,
    ),
    user,
    client,
  };
}
