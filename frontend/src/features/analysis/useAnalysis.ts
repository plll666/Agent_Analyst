import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { toUserMessage } from '../../lib/errors'
import { queryKeys } from '../../lib/queryKeys'
import type { Verification } from '../../types/api'
import {
  buildModel,
  fetchModelVersions,
  fetchVerifications,
  startVerification,
} from './analysisApi'

export const POLL_INTERVAL_MS = 2000

const hasPendingVerification = (verifications: Verification[]): boolean =>
  verifications.some((verification) => verification.status === 'PENDING')

export function useModelVersions(projectId: string) {
  return useQuery({
    queryKey: queryKeys.models(projectId),
    queryFn: () => fetchModelVersions(projectId),
    enabled: projectId !== '',
  })
}

export function useVerifications(projectId: string) {
  return useQuery({
    queryKey: queryKeys.verifications(projectId),
    queryFn: () => fetchVerifications(projectId),
    enabled: projectId !== '',
    refetchInterval: (query) => {
      const verifications = query.state.data ?? []

      return hasPendingVerification(verifications) ? POLL_INTERVAL_MS : false
    },
  })
}

export function useStartVerification(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: () => startVerification(projectId),
    onSuccess: (verification) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.verifications(projectId) })
      push({
        tone: 'info',
        title: 'Проверка поставлена в очередь',
        description: 'Статус обновится сам — страницу перезагружать не нужно',
      })
      return verification
    },
  })
}

export function useBuildModel(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: (requirementId: string) => buildModel(projectId, requirementId),
    onSuccess: (model) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.models(projectId) })
      push({
        tone: 'success',
        title: `Модель v${model.version} построена`,
        description: 'Теперь требование можно проверить',
      })
    },
    onError: (error) => {
      push({
        tone: 'danger',
        title: 'Модель не построена',
        description: toUserMessage(error),
      })
    },
  })
}
