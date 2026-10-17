import { useQuery } from '@tanstack/react-query'

import { queryKeys } from '../../lib/queryKeys'
import { fetchCurrentUser } from './authApi'

export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: fetchCurrentUser,
    staleTime: 60_000,
    retry: false,
  })
}
