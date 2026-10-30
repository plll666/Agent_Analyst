import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import {
  decodeCollection,
  decodeLlmCapabilities,
  decodeModelVersion,
  decodeVerification,
} from '../../lib/decode'
import type { LlmCapabilities, ModelVersion, Verification } from '../../types/api'

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
}

export const startAnalysis = (
  projectId: string,
  { requirementId, reasoning }: StartAnalysisPayload,
): Promise<Verification> => {
  const body: Record<string, unknown> = {}

  if (requirementId !== null) {
    body.requirement_id = requirementId
  }
  if (reasoning !== null) {
    body.reasoning = reasoning
  }

  return apiRequest(analysesPath(projectId), decodeVerification, {
    method: HTTP_METHODS.post,
    body,
  })
}

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
