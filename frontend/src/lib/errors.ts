import { API_ERROR_CODES } from '../types/api'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  get isUnauthenticated(): boolean {
    return this.status === 401 || this.code === API_ERROR_CODES.unauthenticated
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === API_ERROR_CODES.notFound
  }
}

export const NETWORK_ERROR_MESSAGE =
  'Сервер недоступен. Проверьте, что API запущен, и повторите попытку.'

export const toUserMessage = (error: unknown): string => {
  if (error instanceof ApiError) {
    return error.message
  }

  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return 'Запрос отменён'
    }

    return NETWORK_ERROR_MESSAGE
  }

  return 'Что-то пошло не так. Попробуйте ещё раз.'
}
