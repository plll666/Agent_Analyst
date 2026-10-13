import { formatState } from '../../lib/expressions'
import type { VerificationCounterexample } from '../../types/api'

export interface CounterexampleStepsProps {
  counterexample: VerificationCounterexample
}

export function CounterexampleSteps({ counterexample }: CounterexampleStepsProps) {
  return (
    <ol className="flex flex-col gap-1.5">
      {counterexample.steps.map((step, index) => (
        <li
          key={step.number}
          className="relative grid gap-1 ps-5 @2xl:grid-cols-[6rem_9rem_minmax(0,1fr)] @2xl:items-baseline @2xl:gap-3"
        >
          {index < counterexample.steps.length - 1 ? (
            <span className="absolute start-[0.45rem] top-5 bottom-[-0.6rem] w-px bg-line" />
          ) : null}

          <span className="font-mono text-micro text-subtle">
            {step.transition === null ? 'старт' : `шаг ${step.number}`}
          </span>

          <span className="font-mono text-xs text-bone">
            {step.transition === null ? '—' : step.transition}
          </span>

          <span className="font-mono text-xs break-words text-muted">
            {formatState(step.state)}
          </span>
        </li>
      ))}
    </ol>
  )
}
