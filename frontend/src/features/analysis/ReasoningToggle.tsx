import { useId } from 'react'

import { cn } from '../../lib/cn'

interface ReasoningToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  className?: string
}

/**
 * Выбор «рассуждать перед ответом».
 *
 * Показывается только тогда, когда бэк подтвердил, что модель умеет рассуждать:
 * иначе галочка обещала бы настройку, которая ничего не меняет. Подпись
 * объясняет смысл словами, без терминов провайдера.
 */
export function ReasoningToggle({
  checked,
  onChange,
  disabled = false,
  className,
}: ReasoningToggleProps) {
  const inputId = useId()

  return (
    <label
      htmlFor={inputId}
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-card border border-line bg-surface/60 p-3 text-left transition-colors hover:border-line-strong',
        disabled && 'cursor-not-allowed opacity-60',
        className,
      )}
    >
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 cursor-pointer accent-bone disabled:cursor-not-allowed"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-medium text-fg">Рассуждать перед ответом</span>
        <span className="text-xs leading-relaxed text-muted">
          Модель сначала продумывает требование, а потом строит модель. Дольше, но точнее на сложных
          правилах.
        </span>
      </span>
    </label>
  )
}
