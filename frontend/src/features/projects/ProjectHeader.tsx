import { useState } from 'react'
import { NavLink } from 'react-router-dom'

import { Button } from '../../components/Button'
import { PageHeader } from '../../components/PageHeader'
import { cn } from '../../lib/cn'
import type { Project } from '../../types/api'
import { ProjectFormDialog } from './ProjectFormDialog'

export type ProjectTab = 'requirement' | 'analysis'

export interface ProjectHeaderProps {
  project: Project
  eyebrow: string
  tab: ProjectTab
}

const TAB_CLASS = 'relative px-3 py-2.5 text-sm transition-colors duration-200 hover:text-fg'

const TAB_ACTIVE_CLASS =
  'text-fg after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:bg-bone'

export function ProjectHeader({ project, eyebrow, tab }: ProjectHeaderProps) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        backTo="/projects"
        backLabel="Все проекты"
        eyebrow={eyebrow}
        title={project.name}
        description={project.description ?? 'Описание проекта не заполнено'}
        actions={
          <Button
            variant="secondary"
            className="w-full @lg:w-auto"
            onClick={() => setIsSettingsOpen(true)}
          >
            Настройки
          </Button>
        }
      />

      <nav className="-mb-6 flex gap-1 border-b border-line">
        <NavLink
          to={`/projects/${project.id}`}
          end
          className={cn(TAB_CLASS, tab === 'requirement' && TAB_ACTIVE_CLASS, 'text-muted')}
        >
          Требование
        </NavLink>
        <NavLink
          to={`/projects/${project.id}/analysis`}
          className={cn(TAB_CLASS, tab === 'analysis' && TAB_ACTIVE_CLASS, 'text-muted')}
        >
          Анализ
        </NavLink>
      </nav>

      <ProjectFormDialog
        open={isSettingsOpen}
        project={project}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}
