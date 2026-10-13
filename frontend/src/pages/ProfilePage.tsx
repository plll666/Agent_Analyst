import { Link } from 'react-router-dom'

import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { ThemeToggle } from '../components/ThemeToggle'
import { useLogout } from '../features/auth/useLogout'
import { useProfileSummary } from '../features/profile/useProfileSummary'
import { toUserMessage } from '../lib/errors'
import {
  formatDateTime,
  pluralizeProjects,
  pluralizeRequirements,
  pluralizeVerifications,
  pluralizeViolations,
} from '../lib/format'

const SECTION_TITLE_CLASS = 'text-micro font-semibold tracking-[0.14em] text-subtle uppercase'

interface StatTileProps {
  value: number
  label: string
  tone?: 'neutral' | 'danger'
}

function StatTile({ value, label, tone = 'neutral' }: StatTileProps) {
  return (
    <div className="flex flex-col gap-1 rounded-field border border-line bg-raised/40 px-4 py-3.5">
      <span
        className={
          tone === 'danger'
            ? 'font-mono text-2xl leading-none text-danger'
            : 'font-mono text-2xl leading-none text-bone'
        }
      >
        {value}
      </span>
      <span className="text-xs text-muted">{label}</span>
    </div>
  )
}

function AccountCard({
  summary,
}: {
  summary: NonNullable<ReturnType<typeof useProfileSummary>['data']>
}) {
  const { user } = summary
  const initials = (user.display_name ?? user.email).slice(0, 1).toUpperCase()

  return (
    <section className="flex flex-col gap-5 rounded-card border border-line bg-surface/70 p-6 shadow-card">
      <h2 className={SECTION_TITLE_CLASS}>Аккаунт</h2>

      <div className="flex items-center gap-4">
        <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-bone/25 bg-bone-soft/50 text-lg font-semibold text-bone">
          {initials}
        </span>
        <div className="min-w-0 space-y-1">
          <p className="text-base font-semibold break-words">{user.display_name ?? 'Без имени'}</p>
          <p className="truncate text-sm text-muted">{user.email}</p>
        </div>
      </div>

      <dl className="grid gap-x-6 gap-y-3 text-sm @md:grid-cols-2">
        <div className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-2">
          <dt className="text-muted">Регистрация</dt>
          <dd className="font-mono text-fg">{formatDateTime(user.created_at)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-2">
          <dt className="text-muted">Последний вход</dt>
          <dd className="font-mono text-fg">
            {user.last_login_at === null ? '—' : formatDateTime(user.last_login_at)}
          </dd>
        </div>
      </dl>
    </section>
  )
}

export function ProfilePage() {
  const summaryQuery = useProfileSummary()
  const logout = useLogout()
  const summary = summaryQuery.data ?? null

  return (
    <div className="flex flex-1 flex-col gap-6 lg:gap-8">
      <PageHeader
        backTo="/projects"
        backLabel="Все проекты"
        eyebrow="Личный кабинет"
        title="Профиль"
        description="Данные аккаунта, сводка по работе и настройки интерфейса"
      />

      {summaryQuery.isPending ? (
        <div className="flex flex-col gap-5">
          <Skeleton className="h-56 rounded-card" />
          <Skeleton className="h-40 rounded-card" />
        </div>
      ) : null}

      {summaryQuery.isError ? (
        <EmptyState
          icon="!"
          title="Профиль недоступен"
          description={toUserMessage(summaryQuery.error)}
          className="flex-1"
          action={
            <Button variant="secondary" onClick={() => void summaryQuery.refetch()}>
              Повторить
            </Button>
          }
        />
      ) : null}

      {summary !== null ? (
        <>
          <AccountCard summary={summary} />

          <section className="flex flex-col gap-5 rounded-card border border-line bg-surface/70 p-6 shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className={SECTION_TITLE_CLASS}>Активность</h2>
              {summary.last_verification_at !== null ? (
                <span className="text-xs text-subtle">
                  Последняя проверка {formatDateTime(summary.last_verification_at)}
                </span>
              ) : null}
            </div>

            <div className="grid gap-3 @md:grid-cols-2 @3xl:grid-cols-4">
              <StatTile
                value={summary.projects_count}
                label={pluralizeProjects(summary.projects_count)}
              />
              <StatTile
                value={summary.requirement_versions_count}
                label={pluralizeRequirements(summary.requirement_versions_count)}
              />
              <StatTile
                value={summary.verification_count}
                label={pluralizeVerifications(summary.verification_count)}
              />
              <StatTile
                value={summary.violation_count}
                label={pluralizeViolations(summary.violation_count)}
                tone={summary.violation_count > 0 ? 'danger' : 'neutral'}
              />
            </div>
          </section>

          <section className="flex flex-col gap-4 rounded-card border border-line bg-surface/70 p-6 shadow-card">
            <div>
              <h2 className={SECTION_TITLE_CLASS}>Оформление</h2>
              <p className="mt-1.5 text-sm text-muted">
                Системная тема следует настройкам операционной системы и переключается сама
              </p>
            </div>
            <ThemeToggle variant="segmented" />
          </section>

          <section className="flex flex-col gap-4 rounded-card border border-line bg-surface/70 p-6 shadow-card">
            <div>
              <h2 className={SECTION_TITLE_CLASS}>Сессия</h2>
              <p className="mt-1.5 text-sm text-muted">
                Выход удаляет cookie сессии — потребуется войти заново
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="danger" loading={logout.isPending} onClick={() => logout.mutate()}>
                Выйти из аккаунта
              </Button>
              <Link to="/projects">
                <Button variant="ghost">К проектам</Button>
              </Link>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
