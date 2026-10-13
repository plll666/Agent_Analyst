import { forwardRef } from 'react'
import type { ComponentProps } from 'react'

import { cn } from '../lib/cn'

export interface TextareaProps extends ComponentProps<'textarea'> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid = false, className, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid}
      className={cn(
        'w-full rounded-field border bg-surface px-3.5 py-3 text-sm leading-relaxed text-fg',
        'transition-colors duration-200 placeholder:text-subtle focus:ring-2 focus:outline-none',
        'field-sizing-fixed resize-none',
        invalid
          ? 'border-danger/60 focus:border-danger focus:ring-danger/25'
          : 'border-line hover:border-line-strong focus:border-bone focus:ring-bone/25',
        className,
      )}
      {...rest}
    />
  )
})
