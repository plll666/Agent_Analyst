import type { PropsWithChildren } from 'react'

import { cn } from '../lib/cn'

export interface FieldProps extends PropsWithChildren {
  id: string
  label: string
  error?: string | null
  hint?: string | null
}

export function Field({ id, label, error = null, hint = null, children }: FieldProps) {
  const message = error ?? hint

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="eyebrow">
        {label}
      </label>
      {children}
      {message !== null ? (
        <p
          id={`${id}-message`}
          className={cn('text-xs', error !== null ? 'text-danger' : 'text-subtle')}
        >
          {message}
        </p>
      ) : null}
    </div>
  )
}
