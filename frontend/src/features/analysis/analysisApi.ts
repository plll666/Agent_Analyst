import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import {
  decodeCollection,
  DecodeError,
  decodeLlmCapabilities,
  decodeModelVersion,
  decodeVerification,
} from '../../lib/decode'
import type {
  AnalysisEvent,
  AnalysisEventPage,
  LlmCapabilities,
  ModelVersion,
  SubmissionMode,
  Verification,
} from '../../types/api'

const modelsPath = (projectId: string): string => `/projects/${projectId}/models`
const analysesPath = (projectId: string): string => `/projects/${projectId}/analyses`

export const fetchModelVersions = (projectId: string): Promise<ModelVersion[]> =>
  apiRequest(modelsPath(projectId), decodeCollection(decodeModelVersion))

export const fetchVerifications = (projectId: string): Promise<Verification[]> =>
  apiRequest(`/projects/${projectId}/verifications`, decodeCollection(decodeVerification))

export interface StartAnalysisPayload {
  requirementId: string | null
  /** null — не выбирать режим: остаётся умолчание провайдера. */
  reasoning: boolean | null
  forceRecompute?: boolean
}

export interface StartAnalysisResponse {
  verification: Verification
  mode: SubmissionMode
}

export const startAnalysis = (
  projectId: string,
  { requirementId, reasoning, forceRecompute = false }: StartAnalysisPayload,
): Promise<StartAnalysisResponse> => {
  const body: Record<string, unknown> = {}

  if (requirementId !== null) {
    body.requirement_id = requirementId
  }
  if (reasoning !== null) {
    body.reasoning = reasoning
  }
  body.force_recompute = forceRecompute

  return apiRequest(
    analysesPath(projectId),
    (value) => {
      if (typeof value !== 'object' || value === null) {
        throw new DecodeError('Ожидался объект прогона')
      }
      const source = value as Record<string, unknown>
      const verification = decodeVerification(source)
      const submission = source['submission']
      const mode =
        typeof submission === 'object' && submission !== null
          ? (submission as Record<string, unknown>)['mode']
          : 'CREATED'
      if (mode !== 'CREATED' && mode !== 'REUSED' && mode !== 'IN_PROGRESS') {
        throw new DecodeError('Неизвестный режим запуска анализа')
      }
      return { verification, mode }
    },
    { method: HTTP_METHODS.post, body },
  )
}

export const cancelAnalysis = (projectId: string, verificationId: string): Promise<Verification> =>
  apiRequest(`${analysesPath(projectId)}/${verificationId}/cancel`, decodeVerification, {
    method: HTTP_METHODS.post,
  })

export const fetchAnalysisEvents = (
  projectId: string,
  verificationId: string,
  afterSeq = 0,
): Promise<AnalysisEventPage> =>
  apiRequest(
    `/projects/${projectId}/verifications/${verificationId}/events?after_seq=${afterSeq}&limit=500`,
    (value) => {
      if (typeof value !== 'object' || value === null) {
        throw new DecodeError('Ожидался список событий')
      }
      const source = value as Record<string, unknown>
      if (!Array.isArray(source['items'])) {
        throw new DecodeError('Ожидался список событий')
      }
      return {
        items: source['items'].map((item) => {
          if (typeof item !== 'object' || item === null) {
            throw new DecodeError('Некорректное событие')
          }
          const event = item as Record<string, unknown>
          const type = event['type']
          if (
            ![
              'run.updated',
              'stage.updated',
              'stage.statistics',
              'agent.rebuild',
              'run.finished',
            ].includes(String(type))
          ) {
            throw new DecodeError(`Неизвестное событие «${String(type)}»`)
          }
          return {
            schema_version: Number(event['schema_version']),
            verification_id: String(event['verification_id']),
            seq: Number(event['seq']),
            occurred_at: String(event['occurred_at']),
            type: type as AnalysisEvent['type'],
            data: (event['data'] ?? {}) as Record<string, unknown>,
          }
        }),
        next_after_seq: Number(source['next_after_seq']),
        has_more: source['has_more'] === true,
      }
    },
  )

export const fetchLlmCapabilities = (): Promise<LlmCapabilities> =>
  apiRequest('/llm/capabilities', decodeLlmCapabilities)

export const answerAnalysis = (
  projectId: string,
  verificationId: string,
  answer: string,
): Promise<Verification> =>
  apiRequest(`${analysesPath(projectId)}/${verificationId}/answer`, decodeVerification, {
    method: HTTP_METHODS.post,
    body: { answer },
  })
