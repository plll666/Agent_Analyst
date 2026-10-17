import { useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { Textarea } from '../../components/Textarea'
import { useToast } from '../../lib/toastContext'
import { cn } from '../../lib/cn'
import { toUserMessage } from '../../lib/errors'
import { validateRequirementText } from '../../lib/validators'
import type { Requirement } from '../../types/api'
import { useSaveRequirement } from './useRequirements'

const PLACEHOLDER = `Опишите поведение модуля обычным языком.

Пример:
1. Заявка создаётся в статусе «Черновик».
2. Отправленный заявкой менеджер может согласовать её или отклонить.
3. После согласования заявка исполняется бухгалтерией.
4. Отклонённую заявку согласовать нельзя.`

export interface RequirementEditorProps {
  projectId: string
  requirement: Requirement | null
  onGoToCurrent: () => void
  onSaved: (requirement: Requirement) => void
}

export function RequirementEditor({
  projectId,
  requirement,
  onGoToCurrent,
  onSaved,
}: RequirementEditorProps) {
  const saveMutation = useSaveRequirement(projectId)
  const { push } = useToast()
  const textAreaRef = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState(requirement?.raw_text ?? '')

  const isDraft = requirement === null
  const isEditable = isDraft || requirement.is_current
  const baseline = (requirement?.raw_text ?? '').trim()
  const trimmed = text.trim()

  const hasChanges = trimmed !== baseline
  const canSave = isEditable && hasChanges && trimmed !== '' && !saveMutation.isPending
  const nextVersion = (requirement?.version ?? 0) + 1
  const words = trimmed === '' ? 0 : trimmed.split(/\s+/u).length

  const handleSave = async () => {
    const error = validateRequirementText(trimmed)

    if (error !== null) {
      push({ tone: 'danger', title: 'Сохранение невозможно', description: error })
      return
    }

    try {
      const saved = await saveMutation.mutateAsync({ raw_text: trimmed })
      onSaved(saved)
    } catch (error) {
      push({ tone: 'danger', title: 'Не удалось сохранить', description: toUserMessage(error) })
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()

      if (canSave) {
        void handleSave()
      }
    }
  }

  return (
    <section className="flex min-w-0 flex-col rounded-card border border-line bg-surface/70 shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold tracking-tight">Текст требования</h2>
          {isDraft ? (
            <Badge tone="bone">Черновик</Badge>
          ) : (
            <Badge tone="neutral">Версия {requirement.version}</Badge>
          )}
        </div>

        {!isEditable ? (
          <Button variant="subtle" size="sm" onClick={onGoToCurrent}>
            Вернуться к текущей версии
          </Button>
        ) : null}
      </header>

      {!isEditable ? (
        <p className="border-b border-line bg-raised/40 px-5 py-2.5 text-xs text-subtle">
          Вы смотрите историческую версию. Правьте текущую — история остаётся неизменной.
        </p>
      ) : null}

      <div className="flex flex-1 flex-col gap-4 p-5">
        <Textarea
          ref={textAreaRef}
          value={text}
          rows={18}
          readOnly={!isEditable}
          spellCheck={false}
          placeholder={PLACEHOLDER}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          className={cn(
            'min-h-[46dvh] font-mono text-mono-body leading-relaxed @lg:min-h-[58dvh]',
            !isEditable && 'opacity-70',
          )}
        />

        {saveMutation.error !== null ? (
          <p role="alert" className="text-sm text-danger">
            {toUserMessage(saveMutation.error)}
          </p>
        ) : null}
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3.5">
        <div className="text-xs text-subtle">
          <span>{text.length} символов</span>
          <span className="px-2 text-line">·</span>
          <span>{words} слов</span>
          {isEditable ? (
            <span className="ms-3 hidden @lg:inline">Ctrl/⌘ + Enter — сохранить</span>
          ) : null}
        </div>

        <Button
          onClick={() => void handleSave()}
          disabled={!canSave}
          loading={saveMutation.isPending}
        >
          {isDraft ? 'Сохранить версию 1' : `Сохранить как версию ${nextVersion}`}
        </Button>
      </footer>
    </section>
  )
}
