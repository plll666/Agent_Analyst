import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { Badge } from '../../components/Badge'
import { cn } from '../../lib/cn'
import { formatDateTime } from '../../lib/format'
import { ANIMATION, MOTION_MEDIA } from '../../lib/motion'
import type { Requirement } from '../../types/api'

export interface VersionHistoryProps {
  versions: Requirement[]
  selectedId: string | null
  onSelect: (version: Requirement) => void
}

export function VersionHistory({ versions, selectedId, onSelect }: VersionHistoryProps) {
  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.from('[data-version-item]', {
          x: -14,
          opacity: 0,
          duration: ANIMATION.fast,
          ease: 'power3.out',
          stagger: ANIMATION.stagger,
        })
      })
    },
    { dependencies: [versions.length] },
  )

  return (
    <section className="rounded-card border border-line bg-surface/70 shadow-card">
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight">История версий</h2>
        <Badge tone="neutral">{versions.length}</Badge>
      </header>

      <ul className="flex max-h-[22rem] flex-col gap-1 overflow-y-auto p-2 @2xl:max-h-[30rem]">
        {versions.map((version) => {
          const isSelected = version.id === selectedId

          return (
            <li key={version.id}>
              <button
                type="button"
                data-version-item
                onClick={() => onSelect(version)}
                aria-current={isSelected}
                className={cn(
                  'flex w-full flex-col gap-1 rounded-field border px-3 py-2.5 text-start transition-colors duration-200',
                  isSelected
                    ? 'border-bone/45 bg-bone-soft/40'
                    : 'border-transparent hover:border-line hover:bg-raised/70',
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">Версия {version.version}</span>
                  {version.is_current ? (
                    <span className="text-micro font-semibold tracking-wide text-bone uppercase">
                      Текущая
                    </span>
                  ) : null}
                </span>
                <span className="text-xs text-subtle">{formatDateTime(version.created_at)}</span>
                <span className="line-clamp-1 text-xs text-muted">{version.raw_text}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
