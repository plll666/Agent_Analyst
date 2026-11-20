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
import { useImportRequirement, useSaveRequirement } from './useRequirements'

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
  const importMutation = useImportRequirement(projectId)
  const { push } = useToast()
  const textAreaRef = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState(requirement?.raw_text ?? '')
  const [sourceImportId, setSourceImportId] = useState<string | null>(null)
  const [sourceFilename, setSourceFilename] = useState<string | null>(null)
  const [importWarnings, setImportWarnings] = useState<string[]>([])

  const isDraft = requirement === null
  const isEditable = isDraft || requirement.is_current
  const baseline = (requirement?.raw_text ?? '').trim()
  const trimmed = text.trim()

  const hasChanges =
    trimmed !== baseline ||
    (sourceImportId !== null && sourceImportId !== (requirement?.source_import_id ?? null))
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
      const saved = await saveMutation.mutateAsync({
        raw_text: trimmed,
        ...(sourceImportId === null ? {} : { source_import_id: sourceImportId }),
      })
      onSaved(saved)
    } catch (error) {
      push({ tone: 'danger', title: 'Не удалось сохранить', description: toUserMessage(error) })
    }
  }

  const handleImport = async (file: File | undefined) => {
    if (file === undefined) return
    const extension = file.name.split('.').at(-1)?.toLowerCase()
    if (extension !== 'txt' && extension !== 'docx') {
      push({
        tone: 'danger',
        title: 'Формат не поддерживается',
        description: 'Выберите файл TXT или DOCX',
      })
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      push({
        tone: 'danger',
        title: 'Файл слишком большой',
        description: 'Максимальный размер — 10 МБ',
      })
      return
    }
    try {
      const imported = await importMutation.mutateAsync(file)
      setText(imported.raw_text)
      setSourceImportId(imported.id)
      setSourceFilename(imported.filename)
      setImportWarnings(imported.warnings.map((warning) => warning.message))
      push({
        tone: 'success',
        title: 'Текст извлечён',
        description: 'Проверьте его и сохраните версию требования',
      })
    } catch (error) {
      push({
        tone: 'danger',
        title: 'Не удалось прочитать файл',
        description: toUserMessage(error),
      })
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
        {isEditable ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-field border border-line bg-raised/30 px-4 py-3">
            <div>
              <p className="text-sm font-medium text-fg">Загрузить из файла</p>
              <p className="mt-1 text-xs text-subtle">
                TXT или DOCX · до 10 МБ. Перед сохранением текст можно отредактировать.
              </p>
              {sourceFilename !== null ? (
                <p className="mt-1 font-mono text-xs text-bone">Предпросмотр: {sourceFilename}</p>
              ) : null}
            </div>
            <label className="inline-flex h-9 cursor-pointer items-center justify-center rounded-lg border border-line bg-surface px-3 text-xs font-medium text-muted transition-colors hover:border-line-strong hover:text-fg">
              {importMutation.isPending ? 'Читаем…' : 'Выбрать файл'}
              <input
                className="sr-only"
                type="file"
                accept=".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disabled={importMutation.isPending || saveMutation.isPending}
                onChange={(event) => {
                  void handleImport(event.currentTarget.files?.[0])
                  event.currentTarget.value = ''
                }}
              />
            </label>
          </div>
        ) : null}
        {importWarnings.map((warning) => (
          <p
            key={warning}
            role="status"
            className="rounded-field border border-warning/30 bg-raised/40 px-3 py-2 text-xs text-muted"
          >
            {warning}
          </p>
        ))}
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
          {sourceFilename !== null && hasChanges ? (
            <span className="ms-3 text-bone">Текст изменён после извлечения</span>
          ) : null}
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
