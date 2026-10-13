import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import { VerificationDetails } from '../features/analysis/VerificationDetails'
import { VerificationHistory } from '../features/analysis/VerificationHistory'
import { VerificationOutcome } from '../features/analysis/VerificationOutcome'
import {
  useModelVersions,
  useStartVerification,
  useVerifications,
} from '../features/analysis/useAnalysis'
import { ProjectHeader } from '../features/projects/ProjectHeader'
import { useProject } from '../features/projects/useProjects'
import { cn } from '../lib/cn'
import { toUserMessage } from '../lib/errors'
import { pluralizeVerifications } from '../lib/format'
import { ANIMATION, MOTION_MEDIA } from '../lib/motion'
import type { Verification } from '../types/api'

const REDUCED_MOTION_MEDIA = '(prefers-reduced-motion: reduce)'

const DETAILS_BOTTOM_GAP_PX = 12
const STICKY_HEADER_EXTRA_PX = 16

const resolveDetailsAnchor = (block: HTMLElement): Element | null =>
  block.querySelector('[data-details-first-card]') ?? block.firstElementChild

const resolveRevealTarget = (anchor: Element): number => {
  const rect = anchor.getBoundingClientRect()
  const headerHeight = document.querySelector('header')?.offsetHeight ?? 0
  const offsetTop = headerHeight + STICKY_HEADER_EXTRA_PX
  const fitsInViewport = rect.height <= window.innerHeight - offsetTop
  const absolute = fitsInViewport
    ? window.scrollY + rect.bottom + DETAILS_BOTTOM_GAP_PX - window.innerHeight
    : window.scrollY + rect.top - offsetTop
  const maxScroll = document.documentElement.scrollHeight - window.innerHeight

  return Math.min(Math.max(absolute, 0), Math.max(maxScroll, 0))
}

export function AnalysisPage() {
  const { projectId = '' } = useParams()
  const projectQuery = useProject(projectId)
  const modelsQuery = useModelVersions(projectId)
  const verificationsQuery = useVerifications(projectId)
  const startMutation = useStartVerification(projectId)

  const rootRef = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLDivElement>(null)
  const detailsRef = useRef<HTMLDivElement>(null)

  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const [selectedVerificationId, setSelectedVerificationId] = useState<string | null>(null)
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isDetailsMounted, setIsDetailsMounted] = useState(false)

  const project = projectQuery.data ?? null
  const models = modelsQuery.data ?? []
  const verifications = verificationsQuery.data ?? []

  const currentModel = models.at(0) ?? null
  const selectedVerification =
    verifications.find((verification) => verification.id === selectedVerificationId) ??
    verifications.at(0) ??
    null
  const verificationModel =
    models.find((model) => model.id === selectedVerification?.model_version_id) ?? currentModel
  const viewedModel =
    models.find((model) => model.id === selectedModelId) ?? verificationModel ?? currentModel

  const isLoading = projectQuery.isPending || modelsQuery.isPending || verificationsQuery.isPending
  const failure = projectQuery.error ?? modelsQuery.error ?? verificationsQuery.error
  const isFailing = projectQuery.isError || modelsQuery.isError || verificationsQuery.isError

  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.from('[data-panel]', {
          y: 18,
          opacity: 0,
          duration: ANIMATION.base,
          ease: 'power3.out',
          stagger: ANIMATION.stagger,
        })
      })
    },
    { scope: rootRef },
  )

  useGSAP(
    () => {
      const element = detailsRef.current

      if (element === null) {
        return
      }

      const anchor = resolveDetailsAnchor(element)
      const targetScroll = anchor === null ? null : resolveRevealTarget(anchor)

      const revealDetails = (behavior: ScrollBehavior): void => {
        if (targetScroll !== null) {
          window.scrollTo({ top: targetScroll, behavior })
        }
      }

      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        if (isDetailsOpen) {
          const columnWidth = heroRef.current?.getBoundingClientRect().width ?? element.offsetWidth
          const fullWidth = element.parentElement?.clientWidth ?? columnWidth

          gsap
            .timeline()
            .fromTo(
              element,
              { width: columnWidth, height: 0, opacity: 0, y: 12 },
              { width: fullWidth, opacity: 1, y: 0, duration: ANIMATION.slow, ease: 'power3.out' },
              0,
            )
            .fromTo(
              element,
              { height: 0 },
              { height: 'auto', duration: ANIMATION.base, ease: 'power3.out' },
              0,
            )
            .eventCallback('onComplete', () => {
              gsap.set(element, { clearProps: 'width,height' })
              revealDetails('smooth')
            })
          return
        }

        gsap.to(element, {
          height: 0,
          opacity: 0,
          duration: ANIMATION.fast,
          ease: 'power2.inOut',
          onComplete: () => {
            setIsDetailsMounted(false)
          },
        })
      })

      media.add(REDUCED_MOTION_MEDIA, () => {
        if (isDetailsOpen) {
          revealDetails('auto')
          return
        }

        setIsDetailsMounted(false)
      })

      return () => {
        gsap.set(element, { clearProps: 'all' })
      }
    },
    { dependencies: [isDetailsOpen], scope: rootRef },
  )

  const handleToggleDetails = () => {
    if (isDetailsOpen) {
      setIsDetailsOpen(false)
      return
    }

    setIsDetailsMounted(true)
    setIsDetailsOpen(true)
  }

  const handleStartVerification = () => {
    startMutation.mutate(undefined, {
      onSuccess: (verification: Verification) => setSelectedVerificationId(verification.id),
    })
  }

  if (isLoading) {
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

  if (isFailing) {
    return (
      <EmptyState
        icon="!"
        title="Анализ недоступен"
        description={toUserMessage(failure)}
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
        icon="!"
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
    <div ref={rootRef} className="flex flex-1 flex-col gap-6 lg:gap-8">
      <ProjectHeader
        project={project}
        tab="analysis"
        eyebrow={pluralizeVerifications(verifications.length)}
      />

      <div className="grid flex-1 items-stretch gap-5 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,19rem)]">
        <div className="order-1 min-w-0">
          <div ref={heroRef} className="h-full">
            {selectedVerification === null ? (
              <EmptyState
                icon="◷"
                title="Проверка ещё не запускалась"
                description="Запустите проверку — она идёт в фоне, результат появится здесь сам, обновлять страницу не нужно."
                className="h-full min-h-72"
                action={
                  <Button
                    disabled={viewedModel === null}
                    loading={startMutation.isPending}
                    onClick={handleStartVerification}
                    size="lg"
                  >
                    Запустить проверку
                  </Button>
                }
              />
            ) : (
              <VerificationOutcome
                verification={selectedVerification}
                isDetailsOpen={isDetailsOpen}
                onToggleDetails={handleToggleDetails}
              />
            )}
          </div>
        </div>

        <aside className="order-2 flex min-w-0 flex-col gap-4">
          <div
            data-panel
            className="flex flex-col gap-3 rounded-card border border-line bg-surface/70 p-5 shadow-card"
          >
            <h2 className="text-sm font-semibold tracking-tight">Проверить заново</h2>
            <p className="text-xs leading-relaxed text-muted">
              {viewedModel === null
                ? 'Сначала нужно построить модель — она появится, когда агент обработает требование'
                : `Проверяется модель v${viewedModel.version} по сохранённому тексту требования`}
            </p>
            <Button
              className="w-full"
              disabled={viewedModel === null}
              loading={startMutation.isPending}
              onClick={handleStartVerification}
            >
              Запустить проверку
            </Button>
          </div>

          <div data-panel className="flex min-h-0 flex-1">
            <VerificationHistory
              verifications={verifications}
              selectedId={selectedVerification?.id ?? null}
              onSelect={(verification) => setSelectedVerificationId(verification.id)}
            />
          </div>
        </aside>

        {isDetailsMounted && selectedVerification !== null ? (
          <div
            ref={detailsRef}
            className="order-3 min-w-0 overflow-hidden @4xl:col-span-2"
            data-details-block
          >
            {models.length > 1 ? (
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <span className="text-micro font-semibold tracking-[0.14em] text-subtle uppercase">
                  Версия модели
                </span>
                {models.map((model) => (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => setSelectedModelId(model.id)}
                    className={cn(
                      'rounded-field border px-2.5 py-1 font-mono text-xs transition-colors duration-200',
                      model.id === viewedModel?.id
                        ? 'border-bone/45 bg-bone-soft/40 text-bone'
                        : 'border-line text-subtle hover:border-line-strong hover:text-fg',
                    )}
                  >
                    v{model.version}
                    {model.id === currentModel?.id ? ' · текущая' : ''}
                  </button>
                ))}
              </div>
            ) : null}

            <VerificationDetails verification={selectedVerification} modelVersion={viewedModel} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
