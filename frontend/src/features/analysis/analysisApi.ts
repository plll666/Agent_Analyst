import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import { decodeCollection, decodeModelVersion, decodeVerification } from '../../lib/decode'
import type { ModelVersion, Verification } from '../../types/api'

const modelsPath = (projectId: string): string => `/projects/${projectId}/models`
const verificationsPath = (projectId: string): string => `/projects/${projectId}/verifications`

export const fetchModelVersions = (projectId: string): Promise<ModelVersion[]> =>
  apiRequest(modelsPath(projectId), decodeCollection(decodeModelVersion))

export const fetchVerifications = (projectId: string): Promise<Verification[]> =>
  apiRequest(verificationsPath(projectId), decodeCollection(decodeVerification))

export const startVerification = (projectId: string): Promise<Verification> =>
  apiRequest(verificationsPath(projectId), decodeVerification, { method: HTTP_METHODS.post })
