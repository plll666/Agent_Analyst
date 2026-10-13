import { useRef, useState } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { ProjectCard } from '../features/projects/ProjectCard'
import { ProjectFormDialog } from '../features/projects/ProjectFormDialog'
import { useProjects } from '../features/projects/useProjects'
import { toUserMessage } from '../lib/errors'
import { pluralizeProjects } from '../lib/format'
import { ANIMATION, MOTION_MEDIA } from '../lib/motion'

export function ProjectsPage() {
  const projectsQuery = useProjects()
  const rootRef = useRef<HTMLDivElement>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const projects = projectsQuery.data ?? []
  const isLoading = projectsQuery.isPending

  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.from('[data-page-intro]', {
          y: 18,
          opacity: 0,
          duration: ANIMATION.base,
          ease: 'power3.out',
          stagger: 0.08,
        })

        gsap.from('[data-project-card]', {
          y: 22,
          opacity: 0,
          duration: ANIMATION.base,
          ease: 'power3.out',
          stagger: ANIMATION.stagger,
          delay: 0.1,
        })
      })
    },
    { scope: rootRef, dependencies: [projects.length, isLoading] },
  )

  const handleOpenDialog = () => setIsDialogOpen(true)
  const handleCloseDialog = () => setIsDialogOpen(false)

  return (
    <div ref={rootRef} className="flex flex-1 flex-col gap-6 lg:gap-8">
      <div data-page-intro>
        <PageHeader
          eyebrow="Рабочее пространство"
          title="Проекты"
          description="Проект хранит требование и его версии. Начните с описания поведения модуля — остальное приложение сделает само."
          actions={
            <Button onClick={handleOpenDialog} className="w-full @lg:w-auto">
              <span className="text-base leading-none">+</span>
              Новый проект
            </Button>
          }
        />
      </div>

      {isLoading ? (
        <div data-page-intro className="flex items-center gap-3">
          <Skeleton className="size-6 rounded-full" />
          <Skeleton className="h-3 w-32" />
        </div>
      ) : (
        <div data-page-intro className="flex items-center gap-3 text-sm text-muted">
          <span className="flex size-6 items-center justify-center rounded-full border border-bone/30 bg-bone-soft/50 text-micro font-semibold text-bone">
            {projects.length}
          </span>
          <span>{pluralizeProjects(projects.length)}</span>
        </div>
      )}

      {projectsQuery.isError ? (
        <EmptyState
          icon="!"
          title="Не удалось загрузить проекты"
          description={toUserMessage(projectsQuery.error)}
          className="flex-1"
          action={
            <Button variant="secondary" onClick={() => void projectsQuery.refetch()}>
              Повторить
            </Button>
          }
        />
      ) : null}

      {isLoading ? (
        <div className="grid flex-1 content-start gap-4 grid-cols-[repeat(auto-fit,minmax(17rem,1fr))]">
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} className="h-44 rounded-card" />
          ))}
        </div>
      ) : null}

      {projects.length === 0 && projectsQuery.isSuccess ? (
        <EmptyState
          icon="◇"
          title="Пока нет ни одного проекта"
          description="Создайте проект, вставьте текст требования — и сохраните первую версию. Дальше анализ пойдёт по версиям, а не по одному перезаписанному тексту."
          className="flex-1"
          action={
            <Button onClick={handleOpenDialog} size="lg">
              Создать первый проект
            </Button>
          }
        />
      ) : null}

      {projects.length > 0 ? (
        <div className="grid flex-1 content-start gap-4 grid-cols-[repeat(auto-fit,minmax(17rem,1fr))]">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      ) : null}

      <ProjectFormDialog open={isDialogOpen} onClose={handleCloseDialog} />
    </div>
  )
}
