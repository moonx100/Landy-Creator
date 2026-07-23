import { QueryClient } from '@tanstack/react-query';

/**
 * Singleton QueryClient exported so the auth context can call
 * queryClient.clear() on logout, preventing cross-user cache leakage.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 5 * 60_000 },
  },
});
