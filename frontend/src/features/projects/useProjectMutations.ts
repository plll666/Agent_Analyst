import { useMutation, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { queryKeys } from '../../lib/queryKeys'
import type { ProjectPatch, ProjectPayload } from '../../types/api'
import { createProject, updateProject } from './projectsApi'

export function useCreateProject() {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: (payload: ProjectPayload) => createProject(payload),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      push({ tone: 'success', title: 'Проект создан', description: project.name })
    },
  })
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: (payload: ProjectPatch) => updateProject(projectId, payload),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects })
      void queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) })
      push({ tone: 'success', title: 'Проект обновлён', description: project.name })
    },
  })
}
