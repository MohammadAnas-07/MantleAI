import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api/errors";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        refetchOnWindowFocus: false,
        // A 4xx won't get better by asking again; a dropped connection might.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400) && count < 2,
      },
      mutations: { retry: false },
    },
  });
}
