import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '../lib/errors'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.isUnauthenticated) && failureCount < 2,
    },
    mutations: {
      retry: false,
    },
  },
})
