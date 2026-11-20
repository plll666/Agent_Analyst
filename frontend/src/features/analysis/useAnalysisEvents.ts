import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { API_BASE_URL } from '../../lib/apiClient'
import { queryKeys } from '../../lib/queryKeys'
import type { AnalysisEvent, AnalysisStage, Verification } from '../../types/api'
import { fetchAnalysisEvents } from './analysisApi'

const isRunning = (verification: Verification): boolean =>
  verification.execution_status === 'QUEUED' ||
  verification.execution_status === 'RUNNING' ||
  verification.execution_status === 'CANCELLING' ||
  (verification.execution_status === undefined && verification.status === 'PENDING')

const readStage = (event: AnalysisEvent): AnalysisStage | null => {
  const stage = event.data['stage']
  if (typeof stage !== 'object' || stage === null) return null
  const value = stage as Partial<AnalysisStage>
  if (typeof value.stage_id !== 'string' || typeof value.name !== 'string') return null
  return value as AnalysisStage
}

export function useAnalysisEvents(projectId: string, verification: Verification | null) {
  const queryClient = useQueryClient()
  const verificationId = verification?.id ?? ''
  const [liveEvents, setLiveEvents] = useState<AnalysisEvent[]>([])
  const [streamState, setStreamState] = useState<'connecting' | 'connected' | 'offline'>('offline')
  const active = verification !== null && isRunning(verification)

  useEffect(() => {
    setLiveEvents([])
    setStreamState(active ? 'connecting' : 'offline')
  }, [verificationId, active])

  const savedQuery = useQuery({
    queryKey: queryKeys.analysisEvents(projectId, verificationId),
    queryFn: () => fetchAnalysisEvents(projectId, verificationId),
    enabled: projectId !== '' && verificationId !== '' && active,
    refetchInterval: active ? 3000 : false,
    retry: false,
  })

  useEffect(() => {
    if (!active || verificationId === '') return
    const url = new URL(
      `${API_BASE_URL}/projects/${projectId}/verifications/${verificationId}/events/stream`,
      window.location.origin,
    )
    url.searchParams.set('after_seq', String(verification?.last_event_seq ?? 0))
    const source = new EventSource(url, { withCredentials: true })
    source.onopen = () => setStreamState('connected')
    source.onerror = () => setStreamState('offline')
    const handleEvent = (message: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(message.data) as AnalysisEvent
        if (parsed.verification_id !== verificationId || typeof parsed.seq !== 'number') return
        setLiveEvents((current) => {
          if (current.some((item) => item.seq === parsed.seq)) return current
          return [...current, parsed].sort((left, right) => left.seq - right.seq)
        })
        if (parsed.type === 'run.finished') {
          void queryClient.invalidateQueries({ queryKey: queryKeys.verifications(projectId) })
        }
      } catch {
      }
    }
    const eventTypes = [
      'run.updated',
      'stage.updated',
      'stage.statistics',
      'agent.rebuild',
      'run.finished',
    ]
    for (const eventType of eventTypes)
      source.addEventListener(eventType, handleEvent as EventListener)
    return () => source.close()
  }, [active, projectId, queryClient, verification?.last_event_seq, verificationId])

  const events = useMemo(() => {
    const combined = new Map<number, AnalysisEvent>()
    for (const event of savedQuery.data?.items ?? []) combined.set(event.seq, event)
    for (const event of liveEvents) combined.set(event.seq, event)
    return [...combined.values()].sort((left, right) => left.seq - right.seq)
  }, [liveEvents, savedQuery.data?.items])

  const stages = useMemo(() => {
    const current = new Map<string, AnalysisStage>()
    for (const stage of verification?.active_stages ?? []) current.set(stage.stage_id, stage)
    for (const event of events) {
      const stage = readStage(event)
      if (stage !== null) current.set(stage.stage_id, stage)
    }
    return [...current.values()].sort((left, right) => {
      const a = left.started_at === null ? 0 : Date.parse(left.started_at)
      const b = right.started_at === null ? 0 : Date.parse(right.started_at)
      return a - b
    })
  }, [events, verification?.active_stages])

  return {
    events,
    stages,
    streamState,
    isLoading: savedQuery.isLoading,
    isUnavailable: savedQuery.isError && liveEvents.length === 0,
  }
}
