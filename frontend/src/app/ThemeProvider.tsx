import { useCallback, useEffect, useMemo, useState } from 'react'
import type { PropsWithChildren } from 'react'

import type { ResolvedTheme, ThemePreference } from '../lib/theme'
import { applyTheme, readStoredPreference, resolveTheme, storePreference } from '../lib/theme'
import { ThemeContext } from '../lib/themeContext'
import type { ThemeApi } from '../lib/themeContext'

const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)'

export function ThemeProvider({ children }: PropsWithChildren) {
  const [preference, setStoredPreference] = useState<ThemePreference>(() => readStoredPreference())
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme('system'))

  useEffect(() => {
    const media = window.matchMedia(DARK_SCHEME_QUERY)

    const sync = () => {
      const next = resolveTheme(preference)

      applyTheme(next)
      setResolved(next)
    }

    sync()
    media.addEventListener('change', sync)

    return () => media.removeEventListener('change', sync)
  }, [preference])

  const setPreference = useCallback((next: ThemePreference) => {
    storePreference(next)
    setStoredPreference(next)
  }, [])

  const value = useMemo<ThemeApi>(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
