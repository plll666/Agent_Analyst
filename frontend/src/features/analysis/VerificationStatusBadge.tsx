import { Badge } from '../../components/Badge'
import { cn } from '../../lib/cn'
import { VERIFICATION_STATUSES } from '../../types/api'
import type { VerificationStatus } from '../../types/api'
import { VERIFICATION_STATUS_META } from './verificationStatus'

export interface VerificationStatusBadgeProps {
  status: VerificationStatus
  detailed?: boolean
  className?: string
}

export function VerificationStatusBadge({
  status,
  detailed = false,
  className,
}: VerificationStatusBadgeProps) {
  const meta = VERIFICATION_STATUS_META[status]

  const dotClassName = cn('size-1.5 rounded-full', {
    'animate-pulse bg-bone': meta.isPending,
    'bg-success': status === VERIFICATION_STATUSES.propertyHolds,
    'bg-danger': meta.tone === 'danger',
  })

  return (
    <Badge tone={meta.tone} className={cn('gap-2', className)}>
      <span className={dotClassName} />
      {detailed ? meta.headline : meta.shortLabel}
    </Badge>
  )
}
