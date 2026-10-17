import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-4 rounded-card border border-dashed border-line bg-surface/40 px-6 py-14 text-center',
        className,
      )}
    >
      <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-bone/25 bg-bone-soft/40 text-bone">
        {icon}
      </span>
      <div className="max-w-md space-y-1.5">
        <p className="text-base font-semibold break-words">{title}</p>
        <p className="text-sm leading-relaxed text-balance text-muted">{description}</p>
      </div>
      {action}
    </div>
  )
}
