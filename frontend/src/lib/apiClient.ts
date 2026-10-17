import { decodeApiErrorDetail, DecodeError } from './decode'
import type { Decoder } from './decode'
import { ApiError } from './errors'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export const HTTP_METHODS = {
  get: 'GET',
  post: 'POST',
  patch: 'PATCH',
  delete: 'DELETE',
} as const

export type HttpMethod = (typeof HTTP_METHODS)[keyof typeof HTTP_METHODS]

const UNAUTHENTICATED_SILENT_PATHS = new Set([
  '/auth/login',
  '/auth/register',
  '/auth/logout',
  '/auth/me',
])

export interface RequestOptions {
  method?: HttpMethod
  body?: unknown
  signal?: AbortSignal
}

type SessionExpiredHandler = () => void

let sessionExpiredHandler: SessionExpiredHandler | null = null

export const setSessionExpiredHandler = (handler: SessionExpiredHandler | null): void => {
  sessionExpiredHandler = handler
}

export const apiRequest = async <T>(
  path: string,
  decode: Decoder<T>,
  options: RequestOptions = {},
): Promise<T> => {
  const { method = HTTP_METHODS.get, body, signal } = options

  const init: RequestInit = { method, credentials: 'include' }

  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }

  if (signal !== undefined) {
    init.signal = signal
  }

  const response = await fetch(`${API_BASE_URL}${path}`, init)

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    const detail = decodeApiErrorDetail(payload)

    if (response.status === 401 && !UNAUTHENTICATED_SILENT_PATHS.has(path)) {
      sessionExpiredHandler?.()
    }

    throw new ApiError(response.status, detail.code, detail.message)
  }

  if (response.status === 204) {
    return decode(undefined)
  }

  const payload: unknown = await response.json().catch(() => null)

  try {
    return decode(payload)
  } catch (error) {
    if (error instanceof DecodeError) {
      throw error
    }

    throw new DecodeError('Ответ сервера не соответствует контракту')
  }
}
