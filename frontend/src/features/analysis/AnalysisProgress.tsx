import { formatDuration } from '../../lib/format'
import type { AnalysisStage, Verification } from '../../types/api'

const STAGE_LABELS: Record<string, string> = {
  build: 'Построение модели',
  gate: 'Проверки модели',
  check: 'Проверка свойств',
  explain: 'Объяснение результата',
  validate: 'Валидация модели',
  compile_tla: 'Генерация TLA+',
  sany_check: 'Проверка синтаксиса SANY',
  tlc_run: 'Запуск TLC',
  parse_result: 'Разбор результата',
}

const STATE_LABELS: Record<AnalysisStage['state'], string> = {
  RUNNING: 'Выполняется',
  SUCCEEDED: 'Готово',
  FAILED: 'Ошибка',
  CANCELLED: 'Отменён',
  SKIPPED: 'Пропущен',
}

function StageRow({ stage }: { stage: AnalysisStage }) {
  const duration =
    stage.duration_ms ??
    (stage.state === 'RUNNING' && stage.started_at !== null
      ? Math.max(0, Date.now() - Date.parse(stage.started_at))
      : null)

  return (
    <li className="grid gap-1 border-b border-line/60 py-2 last:border-0 @md:grid-cols-[minmax(0,1fr)_auto_auto] @md:items-center @md:gap-3">
      <div className="min-w-0">
        <p className="truncate text-sm text-fg">
          {STAGE_LABELS[stage.name] ?? stage.name}
          {stage.scope === 'core' ? (
            <span className="ms-2 text-micro text-subtle">ЯДРО</span>
          ) : null}
          {stage.build_index === null ? '' : ` · шаг ${stage.build_index + 1}`}
          {stage.attempt > 1 ? ` · попытка ${stage.attempt}` : ''}
        </p>
        {stage.property_id !== null ? (
          <p className="mt-0.5 font-mono text-micro text-subtle">Свойство {stage.property_id}</p>
        ) : null}
        {stage.message !== null ? <p className="mt-1 text-xs text-muted">{stage.message}</p> : null}
        {stage.reason_code !== null ? (
          <p className="mt-1 font-mono text-micro text-danger">{stage.reason_code}</p>
        ) : null}
      </div>
      <span
        className={
          stage.state === 'FAILED'
            ? 'text-xs text-danger'
            : stage.state === 'SUCCEEDED'
              ? 'text-xs text-success'
              : stage.state === 'RUNNING'
                ? 'text-xs text-bone'
                : 'text-xs text-subtle'
        }
      >
        {STATE_LABELS[stage.state]}
      </span>
      {duration === null ? null : (
        <span className="font-mono text-xs text-subtle">{formatDuration(duration)}</span>
      )}
      {stage.statistics === null ? null : (
        <p className="text-xs text-subtle @md:col-span-3">
          TLC: {stage.statistics.states_generated} состояний · глубина {stage.statistics.depth}
        </p>
      )}
    </li>
  )
}

export interface AnalysisProgressProps {
  verification: Verification
  stages: AnalysisStage[]
  streamState: 'connecting' | 'connected' | 'offline'
  onCancel?: () => void
  isCancelling?: boolean
}

export function AnalysisProgress({
  verification,
  stages,
  streamState,
  onCancel,
  isCancelling = false,
}: AnalysisProgressProps) {
  const state = verification.execution_status
  const isActive = state === 'QUEUED' || state === 'RUNNING' || state === 'CANCELLING'
  return (
    <section
      aria-live="polite"
      className="flex flex-col gap-3 rounded-field border border-line bg-raised/30 px-4 py-3.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-fg">Ход анализа</h3>
          <p className="mt-1 text-xs text-subtle">
            {state === 'QUEUED'
              ? 'Ожидает запуска'
              : state === 'CANCELLING'
                ? 'Останавливаем текущий этап…'
                : 'Этапы агента и ядра'}
            {streamState === 'offline' ? ' · обновление через сервер' : ''}
          </p>
        </div>
        {isActive && onCancel !== undefined ? (
          <button
            type="button"
            className="rounded-field border border-danger/30 px-3 py-1.5 text-xs text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
            disabled={isCancelling || state === 'CANCELLING'}
            onClick={onCancel}
          >
            {isCancelling || state === 'CANCELLING' ? 'Отменяем…' : 'Отменить анализ'}
          </button>
        ) : null}
      </div>
      {stages.length === 0 ? (
        <p className="text-xs text-subtle">
          {streamState === 'offline'
            ? 'Этапы пока недоступны. Итоговый статус обновляется автоматически.'
            : 'Ожидаем первое событие от сервера.'}
        </p>
      ) : (
        <ol className="flex flex-col">
          {stages.map((stage) => (
            <StageRow key={stage.stage_id} stage={stage} />
          ))}
        </ol>
      )}
    </section>
  )
}
