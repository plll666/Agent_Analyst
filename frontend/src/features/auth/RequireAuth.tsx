import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { FullPageLoader } from '../../components/FullPageLoader'
import { ApiError } from '../../lib/errors'
import { useSession } from './useSession'

export function RequireAuth() {
  const session = useSession()
  const location = useLocation()

  const from = encodeURIComponent(`${location.pathname}${location.search}`)
  const lostSession = session.data !== undefined && session.error instanceof ApiError

  if (session.isPending) {
    return <FullPageLoader />
  }

  if (lostSession) {
    return <Navigate to={`/login?reason=expired&from=${from}`} replace />
  }

  if (session.data === undefined) {
    return <Navigate to={`/login?from=${from}`} replace />
  }

  return <Outlet />
}
