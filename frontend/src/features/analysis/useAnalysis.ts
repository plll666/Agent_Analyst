import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { toUserMessage } from '../../lib/errors'
import { queryKeys } from '../../lib/queryKeys'
import type { Verification } from '../../types/api'
import {
  answerAnalysis,
  cancelAnalysis,
  fetchLlmCapabilities,
  fetchModelVersions,
  fetchVerifications,
  startAnalysis,
} from './analysisApi'
import type { StartAnalysisPayload } from './analysisApi'

export const POLL_INTERVAL_MS = 2000

const hasPendingVerification = (verifications: Verification[]): boolean =>
  verifications.some((verification) => verification.status === 'PENDING')

export interface AnswerPayload {
  verificationId: string
  answer: string
}

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

export function useLlmCapabilities() {
  return useQuery({
    queryKey: queryKeys.llmCapabilities,
    queryFn: fetchLlmCapabilities,
    // Возможности модели меняются только вместе с настройками сервера.
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
}

export function useStartAnalysis(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: (payload: StartAnalysisPayload) => startAnalysis(projectId, payload),
    onSuccess: ({ verification, mode }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.verifications(projectId) })
      push({
        tone: mode === 'REUSED' ? 'success' : 'info',
        title:
          mode === 'REUSED'
            ? 'Показан сохранённый результат'
            : mode === 'IN_PROGRESS'
              ? 'Открыт текущий прогон'
              : 'Анализ запущен',
        description:
          mode === 'REUSED'
            ? 'Для этой версии требования и настроек уже есть завершённый результат'
            : mode === 'IN_PROGRESS'
              ? 'Повторная задача не создавалась'
              : 'Агент построит модель и проверит её — статус обновится сам',
      })
      return verification
    },
    onError: (error) => {
      push({
        tone: 'danger',
        title: 'Анализ не запущен',
        description: toUserMessage(error),
      })
    },
  })
}

export function useCancelAnalysis(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  return useMutation({
    mutationFn: (verificationId: string) => cancelAnalysis(projectId, verificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.verifications(projectId) })
    },
    onError: (error) => {
      push({
        tone: 'danger',
        title: 'Не удалось отменить анализ',
        description: toUserMessage(error),
      })
    },
  })
}

export function useAnswerAnalysis(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: ({ verificationId, answer }: AnswerPayload) =>
      answerAnalysis(projectId, verificationId, answer),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.verifications(projectId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.models(projectId) })
      // Ответ становится новой версией требования: список версий тоже устарел.
      void queryClient.invalidateQueries({ queryKey: queryKeys.requirements(projectId) })
      push({
        tone: 'info',
        title: 'Уточнение принято',
        description: 'Агент строит модель по новой версии требования',
      })
    },
    onError: (error) => {
      push({
        tone: 'danger',
        title: 'Уточнение не отправлено',
        description: toUserMessage(error),
      })
    },
  })
}
