import { createContext, useContext } from 'react'

import type { ResolvedTheme, ThemePreference } from './theme'

export interface ThemeApi {
  preference: ThemePreference
  resolved: ResolvedTheme
  setPreference: (preference: ThemePreference) => void
}

export const ThemeContext = createContext<ThemeApi | null>(null)

export function useTheme(): ThemeApi {
  const context = useContext(ThemeContext)

  if (context === null) {
    throw new Error('useTheme работает только внутри ThemeProvider')
  }

  return context
}
