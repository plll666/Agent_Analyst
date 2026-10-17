import { describe, expect, it } from 'vitest'

import { API_ERROR_CODES } from '../types/api'
import { ApiError, NETWORK_ERROR_MESSAGE, toUserMessage } from './errors'

describe('ApiError', () => {
  it('считает сессию истёкшей по коду 401', () => {
    expect(
      new ApiError(401, API_ERROR_CODES.unauthenticated, 'Сессия истекла').isUnauthenticated,
    ).toBe(true)
  })

  it('не считает сессию истёкшей по коду 403', () => {
    expect(new ApiError(403, API_ERROR_CODES.validation, 'Нет доступа').isUnauthenticated).toBe(
      false,
    )
  })

  it('узнаёт отсутствие ресурса по коду 404', () => {
    expect(new ApiError(404, API_ERROR_CODES.notFound, 'Проект не найден').isNotFound).toBe(true)
  })
})

describe('toUserMessage', () => {
  it('показывает сообщение сервера как есть', () => {
    expect(toUserMessage(new ApiError(400, 'VALIDATION_ERROR', 'Название обязательно'))).toBe(
      'Название обязательно',
    )
  })

  it('объясняет, что сервер недоступен, при сетевой ошибке', () => {
    expect(toUserMessage(new TypeError('Failed to fetch'))).toBe(NETWORK_ERROR_MESSAGE)
  })

  it('отличает отменённый запрос от сетевой ошибки', () => {
    const aborted = new Error('aborted')
    aborted.name = 'AbortError'

    expect(toUserMessage(aborted)).toBe('Запрос отменён')
  })

  it('подставляет запасной текст для неизвестной ошибки', () => {
    expect(toUserMessage('просто строка')).toBe('Что-то пошло не так. Попробуйте ещё раз.')
  })
})
