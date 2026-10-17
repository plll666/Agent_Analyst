import { cn } from '../lib/cn'

export interface LogoProps {
  className?: string
}

export function Logo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-8 text-bone', className)}>
      <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="9" fill="currentColor" opacity="0.1" />
      <rect
        x="0.75"
        y="0.75"
        width="30.5"
        height="30.5"
        rx="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        opacity="0.55"
      />
      <path
        d="M9.5 21.5 16 10.5l6.5 11"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="10.5" r="2.5" fill="currentColor" />
      <circle cx="9.5" cy="21.5" r="2.5" fill="currentColor" />
      <circle
        cx="22.5"
        cy="21.5"
        r="2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        opacity="0.6"
      />
    </svg>
  )
}
