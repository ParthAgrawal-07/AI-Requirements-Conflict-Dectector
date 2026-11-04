import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";

// Shared query client (Pranshu). Real-time events invalidate or patch its cache (app/socket.ts);
// 4xx answers are never retried — they will not change on a second try.
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) &&
          failureCount < 2,
      },
      mutations: { retry: false },
    },
  });
}
