export const THEME_STORAGE_KEY = 'agent-analyst-theme'

export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const isThemePreference = (value: unknown): value is ThemePreference =>
  value === 'system' || value === 'light' || value === 'dark'

export const readStoredPreference = (): ThemePreference => {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY)

    return isThemePreference(raw) ? raw : 'system'
  } catch {
    return 'system'
  }
}

export const storePreference = (preference: ThemePreference): void => {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    return
  }
}

export const resolveTheme = (preference: ThemePreference): ResolvedTheme => {
  if (preference !== 'system') {
    return preference
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const applyTheme = (theme: ResolvedTheme): void => {
  document.documentElement.dataset.theme = theme
}
