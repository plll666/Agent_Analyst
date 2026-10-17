import { Navigate, Outlet } from 'react-router-dom'

import { FullPageLoader } from '../../components/FullPageLoader'
import { useSession } from './useSession'

export function GuestOnly() {
  const session = useSession()

  if (session.isPending) {
    return <FullPageLoader />
  }

  if (session.data !== undefined) {
    return <Navigate to="/projects" replace />
  }

  return <Outlet />
}
