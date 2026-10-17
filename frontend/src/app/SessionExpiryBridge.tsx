import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useToast } from '../lib/toastContext'
import { setSessionExpiredHandler } from '../lib/apiClient'
import { queryClient } from './queryClient'

export function SessionExpiryBridge() {
  const navigate = useNavigate()
  const location = useLocation()
  const { push } = useToast()

  useEffect(() => {
    setSessionExpiredHandler(() => {
      queryClient.clear()
      push({
        tone: 'danger',
        title: 'Сессия истекла',
        description: 'Войдите заново, чтобы продолжить работу с проектами',
      })
      void navigate(`/login?reason=expired&from=${encodeURIComponent(location.pathname)}`, {
        replace: true,
      })
    })

    return () => setSessionExpiredHandler(null)
  }, [location.pathname, navigate, push])

  return null
}
