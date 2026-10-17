import { cn } from '../lib/cn'
import { useTheme } from '../lib/themeContext'
import type { ThemePreference } from '../lib/theme'
import { Button } from './Button'
import { Icon } from './Icon'

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Системная' },
  { value: 'light', label: 'Светлая' },
  { value: 'dark', label: 'Тёмная' },
]

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
                'flex-1 rounded-field px-3 py-2 text-sm transition-colors duration-200 @md:flex-none',
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
      <Icon name={resolved === 'dark' ? 'moon' : 'sun'} />
    </Button>
  )
}
