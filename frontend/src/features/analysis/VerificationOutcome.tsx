import { useState } from 'react'

import { cn } from '../../lib/cn'
import { formatDateTime } from '../../lib/format'
import { VERIFICATION_STATUSES } from '../../types/api'
import type { Verification } from '../../types/api'
import { Icon } from '../../components/Icon'
import { CounterexampleSteps } from './CounterexampleSteps'
import { EventChain } from './EventChain'
import { VerificationStatusBadge } from './VerificationStatusBadge'
import {
  HOLDS_EXPLANATION,
  INCONCLUSIVE_EXPLANATION,
  VERIFICATION_STATUS_META,
} from './verificationStatus'

const INCONCLUSIVE_STATUSES: Verification['status'][] = [
  VERIFICATION_STATUSES.timeout,
  VERIFICATION_STATUSES.stateLimitReached,
  VERIFICATION_STATUSES.modelInvalid,
  VERIFICATION_STATUSES.engineError,
]

const stripLeadingNumber = (line: string): string => line.replace(/^\d+[.)]\s*/u, '')

function Scenario({ summary }: { summary: string }) {
  const lines = summary
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '')

  if (lines.length === 0) {
    return <p className="text-sm text-subtle">Вывод по проверке пока не сформулирован</p>
  }

  return (
    <ol className="flex flex-col gap-3">
      {lines.map((line) => (
        <li key={line} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
          <span className="mt-0.5 flex size-6 items-center justify-center rounded-full border border-bone/30 bg-bone-soft/40 font-mono text-micro text-bone">
            {lines.indexOf(line) + 1}
          </span>
          <span className="text-[clamp(0.9375rem,0.9rem+0.2cqi,1.0625rem)] leading-relaxed text-fg">
            {stripLeadingNumber(line)}
          </span>
        </li>
      ))}
    </ol>
  )
}

function AdviceBlock({ title, text }: { title: string; text: string }) {
  return (
    <section className="rounded-field border border-line bg-raised/30 px-4 py-3.5">
      <h3 className="eyebrow">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-fg">{text}</p>
    </section>
  )
}

export interface VerificationOutcomeProps {
  verification: Verification
  isDetailsOpen: boolean
  onToggleDetails: () => void
}

export function VerificationOutcome({
  verification,
  isDetailsOpen,
  onToggleDetails,
}: VerificationOutcomeProps) {
  const [isStepsOpen, setIsStepsOpen] = useState(false)

  const meta = VERIFICATION_STATUS_META[verification.status]
  const isHolds = verification.status === VERIFICATION_STATUSES.propertyHolds
  const isInconclusive = INCONCLUSIVE_STATUSES.includes(verification.status)

  return (
    <section className="flex h-full flex-col gap-6 rounded-card border border-line bg-surface/70 p-6 shadow-card @lg:p-8">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <VerificationStatusBadge status={verification.status} detailed />
          <span className="text-xs text-subtle">{formatDateTime(verification.created_at)}</span>
        </div>

        <h2 className="text-title font-semibold">{meta.headline}</h2>
        <p className="max-w-3xl text-sm leading-relaxed text-balance text-muted">
          {meta.explanation}
        </p>
      </header>

      {meta.isPending ? (
        <div className="h-1 w-full overflow-hidden rounded-full bg-raised">
          <div className="h-1 w-1/3 animate-pulse rounded-full bg-bone/70" />
        </div>
      ) : null}

      <section className="flex flex-col gap-3">
        <h3 className="eyebrow">Что произошло</h3>
        <Scenario summary={verification.business_summary} />
      </section>

      {verification.counterexample === null ? null : (
        <section className="flex flex-col gap-3">
          <h3 className="eyebrow">Цепочка событий</h3>
          <EventChain counterexample={verification.counterexample} />

          <button
            type="button"
            aria-expanded={isStepsOpen}
            onClick={() => setIsStepsOpen((opened) => !opened)}
            className="-ms-2 flex w-fit items-center gap-2 px-2 py-1.5 text-sm text-muted transition-colors hover:text-fg"
          >
            <Icon
              name="chevron"
              className={cn(
                'transition-transform duration-200 ease-out-expo',
                isStepsOpen && 'rotate-90',
              )}
            />
            {isStepsOpen ? 'Скрыть состояния по шагам' : 'Показать состояния по шагам'}
          </button>

          {isStepsOpen ? (
            <div className="reveal-steps">
              <CounterexampleSteps counterexample={verification.counterexample} />
            </div>
          ) : null}
        </section>
      )}

      {verification.hypothesis === null ? null : (
        <AdviceBlock title="Что, скорее всего, не так" text={verification.hypothesis} />
      )}

      {verification.question === null ? null : (
        <AdviceBlock title="Что нужно уточнить" text={verification.question} />
      )}

      {verification.related_requirements.length === 0 ? null : (
        <section className="flex flex-col gap-3">
          <h3 className="eyebrow">Связано с требованиями</h3>
          <ul className="flex flex-col gap-2">
            {verification.related_requirements.map((requirement) => (
              <li
                key={requirement.paragraph_ref ?? requirement.quote ?? ''}
                className="flex flex-col gap-1 rounded-field border border-line bg-raised/30 px-3.5 py-3"
              >
                {requirement.paragraph_ref !== null ? (
                  <span className="font-mono text-micro text-bone">
                    {requirement.paragraph_ref}
                  </span>
                ) : null}
                {requirement.quote !== null ? (
                  <p className="text-sm leading-relaxed text-muted">{requirement.quote}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      {isHolds ? (
        <p className="rounded-field border border-line bg-raised/40 px-4 py-3 text-xs leading-relaxed text-muted">
          {HOLDS_EXPLANATION}
        </p>
      ) : null}

      {isInconclusive ? (
        <p
          className={cn(
            'rounded-field border border-danger/30 bg-surface-danger px-4 py-3 text-xs leading-relaxed text-muted',
          )}
        >
          {INCONCLUSIVE_EXPLANATION}
        </p>
      ) : null}

      <div className="mt-auto flex flex-col gap-4 border-t border-line pt-5">
        <button
          type="button"
          onClick={onToggleDetails}
          aria-expanded={isDetailsOpen}
          className="-ms-2 flex w-fit items-center gap-2 px-2 text-sm text-muted transition-colors hover:text-fg"
        >
          <Icon
            name="chevron"
            className={cn(
              'transition-transform duration-200 ease-out-expo',
              isDetailsOpen && 'rotate-90',
            )}
          />
          {isDetailsOpen ? 'Скрыть технические детали' : 'Показать технические детали'}
        </button>
      </div>
    </section>
  )
}
