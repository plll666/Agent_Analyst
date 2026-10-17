import type { ReactNode } from 'react'

import { Badge } from '../../components/Badge'
import { formatDomain, formatEffect, formatExpression, formatLiteral } from '../../lib/expressions'
import { formatDateTime } from '../../lib/format'
import type { BehavioralModel, Expression, ModelVersion } from '../../types/api'
import { PROPERTY_TYPE_LABELS } from './verificationStatus'

const SECTION_TITLE_CLASS = 'eyebrow'

interface ModelSectionProps {
  title: string
  count?: number
  children: ReactNode
}

function ModelSection({ title, count, children }: ModelSectionProps) {
  return (
    <section className="space-y-3">
      <header className="flex items-center gap-2">
        <h3 className={SECTION_TITLE_CLASS}>{title}</h3>
        {count !== undefined ? <span className="text-micro text-subtle">{count}</span> : null}
      </header>
      {children}
    </section>
  )
}

function VariablesGrid({ model }: { model: BehavioralModel }) {
  return (
    <div className="grid gap-2 @2xl:grid-cols-2">
      {model.variables.map((variable) => (
        <div
          key={variable.name}
          className="flex flex-col gap-1.5 rounded-field border border-line bg-raised/40 px-3 py-2.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm text-bone">{variable.name}</span>
            <span className="text-micro tracking-wide text-subtle uppercase">{variable.type}</span>
          </div>
          <p className="font-mono text-xs break-words text-muted">{formatDomain(variable)}</p>
        </div>
      ))}
    </div>
  )
}

function InitialState({ model }: { model: BehavioralModel }) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(model.initial).map(([name, value]) => (
        <span
          key={name}
          className="rounded-field border border-line bg-surface px-2.5 py-1.5 font-mono text-xs text-muted"
        >
          {name} = <span className="text-bone">{formatLiteral(value)}</span>
        </span>
      ))}
    </div>
  )
}

const describeExpression = (expression: Expression | null): string =>
  expression === null ? 'выполняется всегда' : formatExpression(expression)

function TransitionsList({ model }: { model: BehavioralModel }) {
  return (
    <ul className="flex flex-col gap-2">
      {model.transitions.map((transition) => (
        <li
          key={transition.name}
          className="flex flex-col gap-2 rounded-field border border-line bg-raised/30 px-3.5 py-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-sm font-medium text-bone">{transition.name}</span>
            {transition.source_reference !== null ? (
              <Badge tone="neutral">{transition.source_reference}</Badge>
            ) : null}
          </div>

          <dl className="grid gap-1 text-xs @md:grid-cols-[4.5rem_minmax(0,1fr)] @md:gap-2">
            <dt className="font-mono text-subtle">guard</dt>
            <dd className="font-mono break-words text-muted">
              {describeExpression(transition.guard)}
            </dd>

            <dt className="font-mono text-subtle">effects</dt>
            <dd className="font-mono break-words text-muted">
              {transition.effects.length === 0
                ? '—'
                : transition.effects.map(formatEffect).join(', ')}
            </dd>
          </dl>
        </li>
      ))}
    </ul>
  )
}

function PropertiesList({ model }: { model: BehavioralModel }) {
  return (
    <ul className="flex flex-col gap-2">
      {model.properties.map((property) => (
        <li
          key={property.id}
          className="flex flex-col gap-1.5 rounded-field border border-line bg-raised/30 px-3.5 py-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-bone">{property.id}</span>
            <Badge tone="neutral">{PROPERTY_TYPE_LABELS[property.type]}</Badge>
          </div>

          {property.expression !== null ? (
            <p className="font-mono text-xs break-words text-muted">
              {formatExpression(property.expression)}
            </p>
          ) : (
            <p className="text-xs text-subtle">Проверяется движком без явного выражения</p>
          )}

          {property.description !== null ? (
            <p className="text-xs leading-relaxed text-subtle">{property.description}</p>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

export interface ModelViewProps {
  modelVersion: ModelVersion
}

export function ModelView({ modelVersion }: ModelViewProps) {
  const { document: model, validation_errors: validationErrors } = modelVersion

  return (
    <section className="flex flex-col gap-6 rounded-card border border-line bg-surface/70 shadow-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-sm font-semibold tracking-tight">Модель поведения</h2>
          <Badge tone="bone">v{modelVersion.version}</Badge>
          <Badge tone="neutral">{modelVersion.source === 'agent' ? 'Агент' : 'Вручную'}</Badge>
          <Badge tone={modelVersion.validation_status === 'VALID' ? 'success' : 'danger'}>
            {modelVersion.validation_status === 'VALID' ? 'Валидна' : 'Ошибки валидации'}
          </Badge>
        </div>

        <div className="flex items-center gap-3 text-xs text-subtle">
          <span title={modelVersion.schema_hash} className="max-w-40 truncate font-mono">
            {modelVersion.schema_hash.slice(0, 12)}
          </span>
          <span>{formatDateTime(modelVersion.created_at)}</span>
        </div>
      </header>

      {validationErrors.length > 0 ? (
        <ul className="mx-5 space-y-1 rounded-field border border-danger/30 bg-surface-danger px-3.5 py-3 text-xs text-muted">
          {validationErrors.map((error) => (
            <li key={error} className="font-mono">
              {error}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-col gap-6 px-5 pb-6">
        <ModelSection title="Переменные состояния" count={model.variables.length}>
          <VariablesGrid model={model} />
        </ModelSection>

        <ModelSection title="Начальное состояние">
          <InitialState model={model} />
        </ModelSection>

        <ModelSection title="Переходы" count={model.transitions.length}>
          <TransitionsList model={model} />
        </ModelSection>

        <ModelSection title="Проверяемые свойства" count={model.properties.length}>
          <PropertiesList model={model} />
        </ModelSection>
      </div>
    </section>
  )
}
