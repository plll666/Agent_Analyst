import { cn } from '../lib/cn'

export interface SpinnerProps {
  className?: string
}

export function Spinner({ className }: SpinnerProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block size-4 shrink-0 rounded-full border-2 border-current/25 border-t-current animate-spin',
        className,
      )}
    />
  )
}
