import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { cn } from '../../lib/cn'
import { formatDateTime, pluralizeRuns } from '../../lib/format'
import { ANIMATION, MOTION_MEDIA } from '../../lib/motion'
import type { Verification } from '../../types/api'
import { VerificationStatusBadge } from './VerificationStatusBadge'

export interface VerificationHistoryProps {
  verifications: Verification[]
  selectedId: string | null
  onSelect: (verification: Verification) => void
}

export function VerificationHistory({
  verifications,
  selectedId,
  onSelect,
}: VerificationHistoryProps) {
  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.from('[data-run-item]', {
          x: 12,
          opacity: 0,
          duration: ANIMATION.fast,
          ease: 'power3.out',
          stagger: ANIMATION.stagger,
        })
      })
    },
    { dependencies: [verifications.length] },
  )

  return (
    <section className="flex h-full w-full flex-col rounded-card border border-line bg-surface/70 shadow-card">
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold tracking-tight">Прогоны</h2>
        <span className="text-micro text-subtle">{pluralizeRuns(verifications.length)}</span>
      </header>

      <ul className="flex max-h-[26rem] min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
        {verifications.map((verification) => {
          const isSelected = verification.id === selectedId

          return (
            <li key={verification.id}>
              <button
                type="button"
                data-run-item
                onClick={() => onSelect(verification)}
                aria-current={isSelected}
                className={cn(
                  'flex w-full flex-col gap-1.5 rounded-field border px-3 py-2.5 text-start transition-colors duration-200',
                  isSelected
                    ? 'border-bone/45 bg-bone-soft/40'
                    : 'border-transparent hover:border-line hover:bg-raised/70',
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <VerificationStatusBadge status={verification.status} />
                  {verification.property_id !== null ? (
                    <span className="font-mono text-micro text-subtle">
                      {verification.property_id}
                    </span>
                  ) : null}
                </span>
                <span className="text-xs text-subtle">
                  {formatDateTime(verification.created_at)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
