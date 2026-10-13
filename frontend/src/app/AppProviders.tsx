import type { PropsWithChildren } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { BrowserRouter } from 'react-router-dom'

import { ToastProvider } from '../components/Toaster'
import { queryClient } from './queryClient'
import { SessionExpiryBridge } from './SessionExpiryBridge'
import { ThemeProvider } from './ThemeProvider'

gsap.registerPlugin(useGSAP)

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <SessionExpiryBridge />
            {children}
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
