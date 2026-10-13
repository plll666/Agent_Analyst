import { apiRequest } from '../../lib/apiClient'
import { decodeProfileSummary } from '../../lib/decode'
import type { ProfileSummary } from '../../types/api'

export const fetchProfileSummary = (): Promise<ProfileSummary> =>
  apiRequest('/users/me/summary', decodeProfileSummary)
