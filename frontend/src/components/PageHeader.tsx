import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export interface PageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  backTo?: string
  backLabel?: string
  actions?: ReactNode
}

export function PageHeader({
  eyebrow,
  title,
  description,
  backTo,
  backLabel = 'Назад',
  actions,
}: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      {backTo !== undefined ? (
        <Link
          to={backTo}
          className="group -ms-2 inline-flex w-fit items-center gap-2 px-2 py-2 text-sm text-subtle transition-colors hover:text-fg"
        >
          <span className="transition-transform duration-200 ease-out-expo group-hover:-translate-x-0.5">
            ←
          </span>
          {backLabel}
        </Link>
      ) : null}

      <div className="flex flex-col gap-4 @lg:flex-row @lg:flex-wrap @lg:items-start @lg:justify-between">
        <div className="min-w-0 space-y-2">
          {eyebrow !== undefined ? (
            <p className="text-micro font-semibold tracking-[0.18em] text-bone uppercase">
              {eyebrow}
            </p>
          ) : null}

          <h1 className="text-title font-semibold tracking-tight break-words">{title}</h1>

          {description !== undefined ? (
            <p className="max-w-2xl text-sm leading-relaxed text-balance text-muted">
              {description}
            </p>
          ) : null}
        </div>

        {actions !== undefined ? (
          <div className="flex w-full shrink-0 items-center gap-2 @lg:w-auto">{actions}</div>
        ) : null}
      </div>
    </div>
  )
}
