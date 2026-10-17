import { useMutation, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { queryKeys } from '../../lib/queryKeys'
import { login } from './authApi'

export function useLogin() {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: login,
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.session, user)
      push({
        tone: 'success',
        title: 'Добро пожаловать',
        description: user.display_name ?? user.email,
      })
    },
  })
}
