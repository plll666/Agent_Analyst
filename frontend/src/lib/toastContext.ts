import { createContext, useContext } from 'react'

export type ToastTone = 'info' | 'success' | 'danger'

export interface ToastInput {
  tone: ToastTone
  title: string
  description?: string
}

export interface ToastItem extends ToastInput {
  id: number
}

export interface ToastApi {
  push: (toast: ToastInput) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const context = useContext(ToastContext)

  if (context === null) {
    throw new Error('useToast работает только внутри ToastProvider')
  }

  return context
}
