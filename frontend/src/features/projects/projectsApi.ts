import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import { decodeCollection, decodeProject } from '../../lib/decode'
import type { Project, ProjectPatch, ProjectPayload } from '../../types/api'

const PROJECTS_PATH = '/projects'

export const fetchProjects = (): Promise<Project[]> =>
  apiRequest(PROJECTS_PATH, decodeCollection(decodeProject))

export const fetchProject = (projectId: string): Promise<Project> =>
  apiRequest(`${PROJECTS_PATH}/${projectId}`, decodeProject)

export const createProject = (payload: ProjectPayload): Promise<Project> =>
  apiRequest(PROJECTS_PATH, decodeProject, { method: HTTP_METHODS.post, body: payload })

export const updateProject = (projectId: string, payload: ProjectPatch): Promise<Project> =>
  apiRequest(`${PROJECTS_PATH}/${projectId}`, decodeProject, {
    method: HTTP_METHODS.patch,
    body: payload,
  })
