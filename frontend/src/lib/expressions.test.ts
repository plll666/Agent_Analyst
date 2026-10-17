import { describe, expect, it } from 'vitest'

import type { Expression } from '../types/api'
import {
  formatDomain,
  formatEffect,
  formatExpression,
  formatLiteral,
  formatState,
} from './expressions'

describe('formatLiteral', () => {
  it('оборачивает строки в кавычки', () => {
    expect(formatLiteral('Created')).toBe('"Created"')
  })

  it('печатает числа и логические значения как есть', () => {
    expect(formatLiteral(3)).toBe('3')
    expect(formatLiteral(true)).toBe('true')
  })

  it('показывает прочерк вместо отсутствующего значения', () => {
    expect(formatLiteral(null)).toBe('—')
  })
})

describe('formatExpression', () => {
  it('печатает имя переменной', () => {
    expect(formatExpression({ var: 'status' })).toBe('status')
  })

  it('печатает равенство по примеру из кейса', () => {
    expect(formatExpression({ eq: [{ var: 'status' }, 'Created'] })).toBe('status = "Created"')
  })

  it('печатает принадлежность множеству', () => {
    expect(formatExpression({ in: [{ var: 'status' }, ['Created', 'Approved']] })).toBe(
      'status ∈ {"Created", "Approved"}',
    )
  })

  it('печатает конъюнкцию через символ логического и', () => {
    const expression: Expression = {
      and: [{ eq: [{ var: 'status' }, 'Executed'] }, { eq: [{ var: 'cancelled' }, true] }],
    }

    expect(formatExpression(expression)).toBe('status = "Executed" ∧ cancelled = true')
  })
})

describe('formatEffect', () => {
  it('печатает присваивание через :=', () => {
    expect(formatEffect({ operator: 'set', arguments: ['status', 'Approved'] })).toBe(
      'status := "Approved"',
    )
  })

  it('печатает логическое значение без кавычек', () => {
    expect(formatEffect({ operator: 'set', arguments: ['approved', true] })).toBe(
      'approved := true',
    )
  })
})

describe('formatState', () => {
  it('перечисляет полное состояние через запятую', () => {
    expect(formatState({ status: 'Executed', approved: true, cancelled: true, attempts: 0 })).toBe(
      'status = "Executed", approved = true, cancelled = true, attempts = 0',
    )
  })

  it('печатает пустое состояние без лишних символов', () => {
    expect(formatState({})).toBe('')
  })
})

describe('formatDomain', () => {
  it('перечисляет значения перечисления', () => {
    expect(
      formatDomain({
        name: 'status',
        type: 'enum',
        values: ['Created', 'Approved'],
        min: null,
        max: null,
      }),
    ).toBe('Created | Approved')
  })

  it('показывает домен логической переменной', () => {
    expect(
      formatDomain({ name: 'approved', type: 'boolean', values: [], min: null, max: null }),
    ).toBe('true | false')
  })

  it('показывает границы целочисленной переменной', () => {
    expect(formatDomain({ name: 'attempts', type: 'integer', values: [], min: 0, max: 3 })).toBe(
      '0…3',
    )
  })
})
