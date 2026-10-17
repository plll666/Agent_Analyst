import { forwardRef } from 'react'
import type { ComponentProps } from 'react'

import { cn } from '../lib/cn'

export interface InputProps extends ComponentProps<'input'> {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid}
      className={cn(
        'h-11 w-full rounded-field border bg-surface px-3.5 text-sm text-fg transition-colors duration-200',
        'placeholder:text-subtle',
        'focus:ring-2 focus:outline-none',
        invalid
          ? 'border-danger/60 focus:border-danger focus:ring-danger/25'
          : 'border-line hover:border-line-strong focus:border-bone focus:ring-bone/25',
        className,
      )}
      {...rest}
    />
  )
})
