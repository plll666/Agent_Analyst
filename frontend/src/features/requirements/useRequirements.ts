import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { queryKeys } from '../../lib/queryKeys'
import type { RequirementPayload } from '../../types/api'
import { createRequirement, fetchRequirements } from './requirementsApi'

export function useRequirements(projectId: string) {
  return useQuery({
    queryKey: queryKeys.requirements(projectId),
    queryFn: () => fetchRequirements(projectId),
    enabled: projectId !== '',
  })
}

export function useSaveRequirement(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: (payload: RequirementPayload) => createRequirement(projectId, payload),
    onSuccess: (requirement) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.requirements(projectId) })
      push({
        tone: 'success',
        title: `Версия ${requirement.version} сохранена`,
        description: 'Прежний текст остался в истории',
      })
    },
  })
}
