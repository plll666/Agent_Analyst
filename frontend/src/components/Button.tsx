import type { ComponentProps } from 'react'

import { cn } from '../lib/cn'
import { Spinner } from './Spinner'

const VARIANTS = {
  primary: 'bg-bone text-ink hover:bg-bone/90',
  secondary: 'bg-raised text-fg border border-line hover:border-line-strong hover:bg-overlay',
  ghost: 'text-muted hover:bg-raised hover:text-fg',
  subtle: 'bg-bone-soft text-bone border border-bone/20 hover:bg-bone-soft/80',
  danger: 'bg-danger/15 text-danger border border-danger/30 hover:bg-danger/25',
} as const

const SIZES = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-xs',
  md: 'h-10 gap-2 rounded-field px-4 text-sm',
  lg: 'h-12 gap-2.5 rounded-field px-6 text-base',
} as const

export type ButtonVariant = keyof typeof VARIANTS
export type ButtonSize = keyof typeof SIZES

export interface ButtonProps extends ComponentProps<'button'> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  disabled,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled === true || loading}
      aria-busy={loading}
      className={cn(
        'inline-flex select-none items-center justify-center font-medium whitespace-nowrap',
        'transition-[background-color,border-color,color,filter,transform,opacity] duration-200 ease-out-expo',
        'active:scale-[0.985] disabled:pointer-events-none disabled:opacity-55',
        SIZES[size],
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  )
}
