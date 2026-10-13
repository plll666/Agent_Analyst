import { Link } from 'react-router-dom'

import { formatDateTime } from '../../lib/format'
import type { Project } from '../../types/api'

export interface ProjectCardProps {
  project: Project
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link
      to={`/projects/${project.id}`}
      data-project-card
      className="group flex flex-col gap-3 rounded-card border border-line bg-surface/70 p-5 shadow-card transition-[transform,border-color,background-color] duration-300 ease-out-expo hover:-translate-y-1 hover:border-bone/40 hover:bg-raised/70"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold tracking-tight">{project.name}</h3>
        <span className="text-subtle transition-transform duration-300 ease-out-expo group-hover:translate-x-1 group-hover:text-bone">
          →
        </span>
      </div>

      <p className="line-clamp-2 min-h-10 text-sm leading-relaxed text-muted">
        {project.description ?? 'Без описания — откройте проект и добавьте требование'}
      </p>

      <p className="mt-auto text-xs text-subtle">Обновлён {formatDateTime(project.updated_at)}</p>
    </Link>
  )
}
