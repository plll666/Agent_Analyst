import { useQuery } from '@tanstack/react-query'

import { queryKeys } from '../../lib/queryKeys'
import { fetchProfileSummary } from './profileApi'

export function useProfileSummary() {
  return useQuery({
    queryKey: queryKeys.profileSummary,
    queryFn: fetchProfileSummary,
  })
}
