import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import { decodeCollection, decodeRequirement } from '../../lib/decode'
import type { Requirement, RequirementPayload } from '../../types/api'

const requirementsPath = (projectId: string): string => `/projects/${projectId}/requirements`

export const fetchRequirements = (projectId: string): Promise<Requirement[]> =>
  apiRequest(requirementsPath(projectId), decodeCollection(decodeRequirement))

export const createRequirement = (
  projectId: string,
  payload: RequirementPayload,
): Promise<Requirement> =>
  apiRequest(requirementsPath(projectId), decodeRequirement, {
    method: HTTP_METHODS.post,
    body: payload,
  })
