import { Link, useParams } from 'react-router-dom'

import { useDocumentTitle } from '../lib/useDocumentTitle'
import { Icon } from '../components/Icon'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import { ProjectHeader } from '../features/projects/ProjectHeader'
import { useProject } from '../features/projects/useProjects'
import { RequirementWorkspace } from '../features/requirements/RequirementWorkspace'
import { useRequirements } from '../features/requirements/useRequirements'
import { toUserMessage } from '../lib/errors'
import { pluralizeVersions } from '../lib/format'

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const projectQuery = useProject(projectId)
  const requirementsQuery = useRequirements(projectId)

  const project = projectQuery.data ?? null

  useDocumentTitle(project === null ? 'Проект' : `${project.name} · Требования`)
  const versions = requirementsQuery.data ?? []
  const queryFailure = projectQuery.error ?? requirementsQuery.error

  if (projectQuery.isPending || requirementsQuery.isPending) {
    return (
      <div className="flex flex-1 flex-col gap-6 lg:gap-8">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-72 max-w-full" />
          <Skeleton className="h-4 w-full max-w-xl" />
        </div>
        <Skeleton className="min-h-96 flex-1 rounded-card" />
      </div>
    )
  }

  if (projectQuery.isError || requirementsQuery.isError) {
    return (
      <EmptyState
        icon={<Icon name="alert" className="size-5" />}
        title="Проект недоступен"
        description={toUserMessage(queryFailure)}
        className="flex-1"
        action={
          <Link to="/projects">
            <Button variant="secondary">Вернуться к проектам</Button>
          </Link>
        }
      />
    )
  }

  if (project === null) {
    return (
      <EmptyState
        icon={<Icon name="alert" className="size-5" />}
        title="Проект не найден"
        description="Возможно, он удалён или принадлежит другому пользователю"
        className="flex-1"
        action={
          <Link to="/projects">
            <Button variant="secondary">Вернуться к проектам</Button>
          </Link>
        }
      />
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-6 lg:gap-8">
      <ProjectHeader
        project={project}
        tab="requirement"
        eyebrow={pluralizeVersions(versions.length)}
      />

      <div className="flex flex-1 flex-col">
        <RequirementWorkspace projectId={projectId} versions={versions} />
      </div>
    </div>
  )
}
