import type { ComponentProps } from 'react'

import { cn } from '../lib/cn'

const TONES = {
  neutral: 'border-line bg-raised text-muted',
  bone: 'border-bone/30 bg-bone-soft/60 text-bone',
  success: 'border-success/30 bg-success/15 text-success',
  danger: 'border-danger/30 bg-danger/15 text-danger',
} as const

export type BadgeTone = keyof typeof TONES

export interface BadgeProps extends ComponentProps<'span'> {
  tone?: BadgeTone
}

export function Badge({ tone = 'neutral', className, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-micro font-semibold tracking-wide',
        TONES[tone],
        className,
      )}
      {...rest}
    />
  )
}
