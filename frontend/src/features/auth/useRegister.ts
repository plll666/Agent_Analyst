import { useMutation, useQueryClient } from '@tanstack/react-query'

import { useToast } from '../../lib/toastContext'
import { queryKeys } from '../../lib/queryKeys'
import { register } from './authApi'

export function useRegister() {
  const queryClient = useQueryClient()
  const { push } = useToast()

  return useMutation({
    mutationFn: register,
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.session, user)
      push({
        tone: 'success',
        title: 'Аккаунт создан',
        description: 'Можно переходить к первому проекту',
      })
    },
  })
}
