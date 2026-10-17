export const isMockApiEnabled: boolean =
  import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === 'true'
