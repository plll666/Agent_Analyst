import { Badge } from '../../components/Badge'
import { formatDateTime, formatDuration } from '../../lib/format'
import type { ModelVersion, Verification } from '../../types/api'
import { CounterexampleSteps } from './CounterexampleSteps'
import { ModelView } from './ModelView'
import { PROPERTY_TYPE_LABELS } from './verificationStatus'

const SECTION_TITLE_CLASS = 'eyebrow'

export interface VerificationDetailsProps {
  verification: Verification
  modelVersion: ModelVersion | null
}

export function VerificationDetails({ verification, modelVersion }: VerificationDetailsProps) {
  const { statistics } = verification

  return (
    <div className="flex flex-col gap-5">
      <section
        data-details-first-card
        className="flex flex-col gap-3 rounded-card border border-line bg-raised/20 p-5"
      >
        <h3 className={SECTION_TITLE_CLASS}>Параметры прогона</h3>

        <dl className="grid gap-x-6 gap-y-2 text-xs @md:grid-cols-2">
          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Движок</dt>
            <dd className="font-mono text-muted">
              {verification.engine}
              {verification.engine_version === null ? '' : ` ${verification.engine_version}`}
            </dd>
          </div>

          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Длительность</dt>
            <dd className="font-mono text-muted">
              {verification.duration_ms === null ? '—' : formatDuration(verification.duration_ms)}
            </dd>
          </div>

          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Модель</dt>
            <dd className="font-mono text-muted">
              {modelVersion === null ? '—' : `v${modelVersion.version}`}
            </dd>
          </div>

          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Свойство</dt>
            <dd className="font-mono text-muted">{verification.property_id ?? '—'}</dd>
          </div>

          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Хеш схемы</dt>
            <dd
              className="max-w-48 truncate font-mono text-muted"
              title={modelVersion?.schema_hash}
            >
              {modelVersion === null ? '—' : modelVersion.schema_hash.slice(0, 16)}
            </dd>
          </div>

          <div className="flex justify-between gap-3 border-b border-line/60 py-1.5">
            <dt className="text-subtle">Дата прогона</dt>
            <dd className="font-mono text-muted">{formatDateTime(verification.created_at)}</dd>
          </div>

          <div className="flex flex-col gap-1.5 border-b border-line/60 py-1.5 @md:col-span-2">
            <dt className="text-subtle">Свойства модели</dt>
            <dd className="flex flex-wrap gap-1.5">
              {(modelVersion?.document.properties ?? []).map((property) => (
                <Badge key={property.id} tone="neutral">
                  {property.id} · {PROPERTY_TYPE_LABELS[property.type]}
                </Badge>
              ))}
            </dd>
          </div>
        </dl>

        {statistics === null ? null : (
          <div className="grid gap-2 @md:grid-cols-3">
            <div className="rounded-field border border-line bg-surface px-3 py-2">
              <p className="font-mono text-sm text-bone">{statistics.states_generated}</p>
              <p className="text-xs text-subtle">состояний сгенерировано</p>
            </div>
            <div className="rounded-field border border-line bg-surface px-3 py-2">
              <p className="font-mono text-sm text-bone">{statistics.distinct_states}</p>
              <p className="text-xs text-subtle">уникальных</p>
            </div>
            <div className="rounded-field border border-line bg-surface px-3 py-2">
              <p className="font-mono text-sm text-bone">{statistics.depth}</p>
              <p className="text-xs text-subtle">глубина обхода</p>
            </div>
          </div>
        )}

        {verification.error_detail === null ? null : (
          <div className="rounded-field border border-danger/30 bg-surface-danger px-3.5 py-3">
            <p className={SECTION_TITLE_CLASS}>Детали ошибки</p>
            <p className="mt-1.5 font-mono text-xs break-words text-muted">
              {verification.error_detail}
            </p>
          </div>
        )}
      </section>

      {verification.counterexample === null ? null : (
        <section className="flex flex-col gap-3 rounded-card border border-line bg-raised/20 p-5">
          <h3 className={SECTION_TITLE_CLASS}>Контрпример — состояние на каждом шаге</h3>
          <CounterexampleSteps counterexample={verification.counterexample} />
        </section>
      )}

      {modelVersion === null ? null : <ModelView modelVersion={modelVersion} />}
    </div>
  )
}
