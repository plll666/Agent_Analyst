export const MIN_PASSWORD_LENGTH = 8
export const MAX_PROJECT_NAME_LENGTH = 200

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export const validateEmail = (value: string): string | null => {
  const trimmed = value.trim()

  if (trimmed === '') {
    return 'Укажите email'
  }

  if (!EMAIL_PATTERN.test(trimmed)) {
    return 'Email выглядит некорректно'
  }

  return null
}

export const validatePassword = (value: string): string | null => {
  if (value === '') {
    return 'Укажите пароль'
  }

  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Пароль не короче ${MIN_PASSWORD_LENGTH} символов`
  }

  return null
}

export const validateProjectName = (value: string): string | null => {
  const trimmed = value.trim()

  if (trimmed === '') {
    return 'Укажите название проекта'
  }

  if (trimmed.length > MAX_PROJECT_NAME_LENGTH) {
    return `Не длиннее ${MAX_PROJECT_NAME_LENGTH} символов`
  }

  return null
}

export const validateRequirementText = (value: string): string | null =>
  value.trim() === '' ? 'Требование пока пустое' : null
