export const queryKeys = {
  session: ['session'] as const,
  profileSummary: ['profile-summary'] as const,
  projects: ['projects'] as const,
  project: (projectId: string) => ['projects', projectId] as const,
  requirements: (projectId: string) => ['projects', projectId, 'requirements'] as const,
  models: (projectId: string) => ['projects', projectId, 'models'] as const,
  verifications: (projectId: string) => ['projects', projectId, 'verifications'] as const,
}

export const sessionKey = queryKeys.session
