import { describe, expect, it } from 'vitest'

import { VERIFICATION_STATUSES } from '../../types/api'
import { VERIFICATION_STATUS_META } from './verificationStatus'

const ALL_STATUSES = Object.values(VERIFICATION_STATUSES)
const SUCCESS_STATUSES = [VERIFICATION_STATUSES.propertyHolds]
const INCONCLUSIVE_STATUSES = [
  VERIFICATION_STATUSES.timeout,
  VERIFICATION_STATUSES.stateLimitReached,
  VERIFICATION_STATUSES.modelInvalid,
  VERIFICATION_STATUSES.engineError,
]

describe('VERIFICATION_STATUS_META', () => {
  it('описывает все семь статусов контракта', () => {
    expect(ALL_STATUSES).toHaveLength(7)
    expect(Object.keys(VERIFICATION_STATUS_META).sort()).toEqual([...ALL_STATUSES].sort())
  })

  it.each(ALL_STATUSES)('даёт заголовок и объяснение для %s', (status) => {
    const meta = VERIFICATION_STATUS_META[status]

    expect(meta.headline.length).toBeGreaterThan(0)
    expect(meta.explanation.length).toBeGreaterThan(0)
    expect(meta.shortLabel.length).toBeGreaterThan(0)
  })

  it.each(INCONCLUSIVE_STATUSES)('не выдаёт %s за успех', (status) => {
    const meta = VERIFICATION_STATUS_META[status]

    expect(meta.tone).not.toBe('success')
    expect(meta.tone).toBe('danger')
    expect(meta.headline).not.toBe(
      VERIFICATION_STATUS_META[VERIFICATION_STATUSES.propertyHolds].headline,
    )
  })

  it.each(INCONCLUSIVE_STATUSES)('говорит в %s, что вывод делать нельзя', (status) => {
    const meta = VERIFICATION_STATUS_META[status]

    expect(meta.explanation).toMatch(/не установлены|не дала результата|не прошла валидацию/)
  })

  it('помечает только PROPERTY_HOLDS успехом', () => {
    const successful = ALL_STATUSES.filter(
      (status) => VERIFICATION_STATUS_META[status].tone === 'success',
    )

    expect(successful).toEqual(SUCCESS_STATUSES)
  })

  it('различает таймаут и лимит состояний по короткой подписи', () => {
    expect(VERIFICATION_STATUS_META[VERIFICATION_STATUSES.timeout].shortLabel).toBe('Таймаут')
    expect(VERIFICATION_STATUS_META[VERIFICATION_STATUSES.stateLimitReached].shortLabel).toBe(
      'Лимит',
    )
  })

  it('отмечает PENDING как незавершённый', () => {
    const meta = VERIFICATION_STATUS_META[VERIFICATION_STATUSES.pending]

    expect(meta.isPending).toBe(true)
    expect(meta.tone).not.toBe('success')
  })

  it('не отмечает ни один терминальный статус как ожидающий', () => {
    const terminal = ALL_STATUSES.filter((status) => status !== VERIFICATION_STATUSES.pending)

    expect(terminal.every((status) => VERIFICATION_STATUS_META[status].isPending === false)).toBe(
      true,
    )
  })

  it('нарушение показывает как провал, а не как успех', () => {
    const meta = VERIFICATION_STATUS_META[VERIFICATION_STATUSES.propertyViolated]

    expect(meta.tone).toBe('danger')
    expect(meta.headline).toBe('Найдено нарушение')
  })
})
