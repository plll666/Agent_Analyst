import { useQuery } from '@tanstack/react-query'

import { queryKeys } from '../../lib/queryKeys'
import { fetchProject, fetchProjects } from './projectsApi'

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: fetchProjects,
  })
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => fetchProject(projectId),
    enabled: projectId !== '',
  })
}
