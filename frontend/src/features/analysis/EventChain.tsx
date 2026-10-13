import type { VerificationCounterexample } from '../../types/api'

export interface EventChainProps {
  counterexample: VerificationCounterexample
}

export function EventChain({ counterexample }: EventChainProps) {
  const events = counterexample.steps
    .filter((step) => step.transition !== null)
    .map((step) => step.transition ?? '')
  const lastIndex = events.length - 1

  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2">
      {events.map((event, index) => (
        <li key={`${event}-${index}`} className="flex items-center gap-2">
          <span
            className={
              index === lastIndex
                ? 'rounded-field border border-danger/45 bg-surface-danger px-2.5 py-1 font-mono text-xs text-fg'
                : 'rounded-field border border-line bg-raised/60 px-2.5 py-1 font-mono text-xs text-muted'
            }
          >
            {event}
          </span>
          {index < lastIndex ? (
            <span aria-hidden="true" className="text-subtle">
              →
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  )
}
