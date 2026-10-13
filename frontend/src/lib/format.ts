const dateFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

const dateTimeFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export const formatDate = (isoDate: string): string => dateFormatter.format(new Date(isoDate))

export const formatDateTime = (isoDate: string): string =>
  dateTimeFormatter.format(new Date(isoDate))

export const pluralize = (count: number, one: string, few: string, many: string): string => {
  const remainder100 = count % 100
  const remainder10 = count % 10

  if (remainder100 >= 11 && remainder100 <= 14) {
    return `${count} ${many}`
  }

  if (remainder10 === 1) {
    return `${count} ${one}`
  }

  if (remainder10 >= 2 && remainder10 <= 4) {
    return `${count} ${few}`
  }

  return `${count} ${many}`
}

export const pluralizeProjects = (count: number): string =>
  pluralize(count, 'проект', 'проекта', 'проектов')

export const pluralizeVersions = (count: number): string =>
  pluralize(count, 'версия', 'версии', 'версий')

export const formatDuration = (milliseconds: number): string =>
  milliseconds < 1000
    ? `${milliseconds} мс`
    : `${(milliseconds / 1000).toFixed(1).replace('.', ',')} с`

export const pluralizeRuns = (count: number): string =>
  pluralize(count, 'прогон', 'прогона', 'прогонов')

export const pluralizeVerifications = (count: number): string =>
  pluralize(count, 'проверка', 'проверки', 'проверок')

export const pluralizeRequirements = (count: number): string =>
  pluralize(count, 'версия требования', 'версии требований', 'версий требований')

export const pluralizeViolations = (count: number): string =>
  pluralize(count, 'нарушение', 'нарушения', 'нарушений')
