import { cn } from '../lib/cn'
import { useTheme } from '../lib/themeContext'
import type { ThemePreference } from '../lib/theme'
import { Button } from './Button'

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Системная' },
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
]

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4" fill="none" strokeWidth="1.6">
      <circle cx="12" cy="12" r="4" stroke="currentColor" />
      <path
        d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"
        stroke="currentColor"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4" fill="none" strokeWidth="1.6">
      <path
        d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
        stroke="currentColor"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export interface ThemeToggleProps {
  variant: 'icon' | 'segmented'
  className?: string
}

export function ThemeToggle({ variant, className }: ThemeToggleProps) {
  const { preference, resolved, setPreference } = useTheme()

  if (variant === 'segmented') {
    return (
      <div
        role="group"
        aria-label="Оформление"
        className={cn(
          'inline-flex w-full gap-1 rounded-field border border-line bg-raised/50 p-1 @md:w-auto',
          className,
        )}
      >
        {OPTIONS.map((option) => {
          const isActive = preference === option.value

          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={isActive}
              onClick={() => setPreference(option.value)}
              className={cn(
                'flex-1 rounded-[0.5rem] px-3 py-2 text-sm transition-colors duration-200 @md:flex-none',
                isActive ? 'bg-bone text-ink' : 'text-muted hover:bg-raised hover:text-fg',
              )}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    )
  }

  const nextTheme = resolved === 'dark' ? 'light' : 'dark'

  return (
    <Button
      variant="ghost"
      className={cn('h-9 px-2.5 lg:h-10 lg:px-3', className)}
      onClick={() => setPreference(nextTheme)}
      aria-label={nextTheme === 'light' ? 'Включить светлую тему' : 'Включить тёмную тему'}
      title={preference === 'system' ? `Оформление: системное (${resolved})` : undefined}
    >
      {resolved === 'dark' ? <MoonIcon /> : <SunIcon />}
    </Button>
  )
}
