import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { queryClient } from '../../app/queryClient'
import { logout } from './authApi'

export function useLogout() {
  const navigate = useNavigate()

  return useMutation({
    mutationFn: logout,
    onSettled: () => {
      queryClient.clear()
      void navigate('/login', { replace: true })
    },
  })
}
