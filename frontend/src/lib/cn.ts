export type ClassValue = string | false | null | undefined | Record<string, boolean | undefined>

export const cn = (...values: ClassValue[]): string =>
  values
    .flatMap((value) => {
      if (typeof value === 'string') {
        return value.split(/\s+/u).filter(Boolean)
      }

      if (value !== null && typeof value === 'object') {
        return Object.entries(value)
          .filter(([, enabled]) => enabled === true)
          .map(([className]) => className)
      }

      return []
    })
    .join(' ')
