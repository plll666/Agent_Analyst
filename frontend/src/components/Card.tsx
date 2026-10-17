import type { ComponentProps } from 'react'

import { cn } from '../lib/cn'

export function Card({ className, ...rest }: ComponentProps<'section'>) {
  return (
    <section
      className={cn(
        'rounded-card border border-line bg-surface/70 shadow-card backdrop-blur-sm',
        className,
      )}
      {...rest}
    />
  )
}
