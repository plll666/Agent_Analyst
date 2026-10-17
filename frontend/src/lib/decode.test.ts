import { describe, expect, it } from 'vitest'

import { DecodeError } from './decode'
import {
  decodeApiErrorDetail,
  decodeBehavioralModel,
  decodeModelVersion,
  decodeProfileSummary,
  decodeProject,
  decodeRequirement,
  decodeUser,
  decodeVerification,
} from './decode'

const ordersDocument = {
  variables: [
    { name: 'status', type: 'enum', values: ['Created', 'Approved', 'Cancelled', 'Executed'] },
    { name: 'approved', type: 'boolean', min: null, max: null },
    { name: 'attempts', type: 'integer', min: 0, max: 3 },
  ],
  initial: { status: 'Created', approved: false, attempts: 0 },
  transitions: [
    {
      name: 'Approve',
      guard: { eq: [{ var: 'status' }, 'Created'] },
      effects: [{ set: ['status', 'Approved'] }, { set: ['approved', true] }],
      source_reference: 'p3',
    },
  ],
  properties: [
    {
      id: 'P2',
      type: 'forbidden_state',
      expression: {
        and: [{ eq: [{ var: 'status' }, 'Executed'] }, { eq: [{ var: 'cancelled' }, true] }],
      },
      description: 'Отменённую заявку исполнять нельзя',
    },
    { id: 'P4', type: 'deadlock_free', expression: null, description: null },
  ],
}

const verificationFixture = {
  id: 'run-1',
  project_id: 'project-1',
  model_version_id: 'model-2',
  property_id: 'P2',
  status: 'PROPERTY_VIOLATED',
  engine: 'TLC',
  engine_version: '1.7.4',
  statistics: { states_generated: 162, distinct_states: 37, depth: 8 },
  counterexample: {
    steps: [
      {
        number: 0,
        transition: null,
        state: { status: 'Created', approved: false, cancelled: false },
      },
      {
        number: 1,
        transition: 'Approve',
        state: { status: 'Approved', approved: true, cancelled: false },
      },
      {
        number: 2,
        transition: 'Cancel',
        state: { status: 'Cancelled', approved: true, cancelled: true },
      },
      {
        number: 3,
        transition: 'Execute',
        state: { status: 'Executed', approved: true, cancelled: true },
      },
    ],
  },
  related_requirements: [
    { paragraph_ref: 'p3', quote: 'Заявка после согласования может быть исполнена.' },
  ],
  duration_ms: 812,
  error_detail: null,
  business_summary: 'Заявка создана.\nЗаявка согласована.',
  hypothesis: 'В модели нет условия, запрещающего Execute после Cancel',
  question: null,
  created_at: '2026-10-16T09:12:00Z',
}

describe('decodeUser', () => {
  it('читает пользователя с именем и временем входа', () => {
    const user = decodeUser({
      id: 'u-1',
      email: 'analyst@example.com',
      display_name: 'Анна',
      created_at: '2026-08-31T23:47:00Z',
      last_login_at: '2026-10-12T23:47:00Z',
    })

    expect(user).toEqual({
      id: 'u-1',
      email: 'analyst@example.com',
      display_name: 'Анна',
      created_at: '2026-08-31T23:47:00Z',
      last_login_at: '2026-10-12T23:47:00Z',
    })
  })

  it('принимает null в nullable-полях', () => {
    const user = decodeUser({
      id: 'u-1',
      email: 'guest@example.com',
      display_name: null,
      created_at: '2026-08-31T23:47:00Z',
      last_login_at: null,
    })

    expect(user.display_name).toBeNull()
    expect(user.last_login_at).toBeNull()
  })

  it('отвергает объект без обязательного поля', () => {
    expect(() => decodeUser({ id: 'u-1', email: 'a@b.c' })).toThrow(DecodeError)
  })

  it('отвергает не объект', () => {
    expect(() => decodeUser('не объект')).toThrow(DecodeError)
  })
})

describe('decodeProject', () => {
  it('читает проект с описанием', () => {
    const project = decodeProject({
      id: 'p-1',
      name: 'Модуль заявок',
      description: 'Создание и согласование',
      owner_id: 'u-1',
      created_at: '2026-08-31T23:47:00Z',
      updated_at: '2026-10-16T09:12:00Z',
    })

    expect(project.name).toBe('Модуль заявок')
    expect(project.description).toBe('Создание и согласование')
  })

  it('принимает проект без описания', () => {
    const project = decodeProject({
      id: 'p-1',
      name: 'Модуль заявок',
      description: null,
      owner_id: 'u-1',
      created_at: '2026-08-31T23:47:00Z',
      updated_at: '2026-10-16T09:12:00Z',
    })

    expect(project.description).toBeNull()
  })
})

describe('decodeRequirement', () => {
  it('читает версию требования с отметкой текущей', () => {
    const requirement = decodeRequirement({
      id: 'r-2',
      project_id: 'p-1',
      version: 2,
      raw_text: 'Заявка после согласования может быть исполнена.',
      is_current: true,
      created_at: '2026-10-16T09:12:00Z',
    })

    expect(requirement.version).toBe(2)
    expect(requirement.is_current).toBe(true)
  })
})

describe('decodeBehavioralModel', () => {
  it('читает модель кейса: переменные, начальное состояние, переходы и свойства', () => {
    const document_ = decodeBehavioralModel(ordersDocument)

    expect(document_.variables).toHaveLength(3)
    expect(document_.initial).toEqual({ status: 'Created', approved: false, attempts: 0 })
    expect(document_.transitions[0]?.name).toBe('Approve')
    expect(document_.properties).toHaveLength(2)
  })

  it('принимает свойство без выражения', () => {
    const document_ = decodeBehavioralModel(ordersDocument)

    expect(document_.properties[1]?.expression).toBeNull()
  })
})

describe('decodeModelVersion', () => {
  const modelFixture = {
    id: 'm-2',
    project_id: 'p-1',
    version: 2,
    source: 'agent',
    schema_hash: 'a'.repeat(64),
    validation_status: 'VALID',
    validation_errors: [],
    document: ordersDocument,
    created_at: '2026-10-16T09:12:00Z',
  }

  it('читает версию модели', () => {
    const model = decodeModelVersion(modelFixture)

    expect(model.version).toBe(2)
    expect(model.validation_status).toBe('VALID')
    expect(model.document.variables).toHaveLength(3)
  })

  it('отвергает неизвестный источник модели', () => {
    expect(() => decodeModelVersion({ ...modelFixture, source: 'unknown' })).toThrow(DecodeError)
  })

  it('отвергает неизвестный статус валидации', () => {
    expect(() => decodeModelVersion({ ...modelFixture, validation_status: 'MAYBE' })).toThrow(
      DecodeError,
    )
  })

  it('считает отсутствующие ошибки валидации пустым списком', () => {
    const model = decodeModelVersion({ ...modelFixture, validation_errors: null })

    expect(model.validation_errors).toEqual([])
  })
})

describe('decodeVerification', () => {
  it('читает нарушение вместе с контрпримером', () => {
    const verification = decodeVerification(verificationFixture)

    expect(verification.status).toBe('PROPERTY_VIOLATED')
    expect(verification.counterexample?.steps).toHaveLength(4)
  })

  it('начинает контрпример с шага без перехода', () => {
    const verification = decodeVerification(verificationFixture)
    const first = verification.counterexample?.steps[0]

    expect(first?.number).toBe(0)
    expect(first?.transition).toBeNull()
  })

  it('доходит до нарушающего состояния на последнем шаге', () => {
    const verification = decodeVerification(verificationFixture)
    const last = verification.counterexample?.steps.at(-1)

    expect(last?.transition).toBe('Execute')
    expect(last?.state).toEqual({
      status: 'Executed',
      approved: true,
      cancelled: true,
    })
  })

  it('читает успешную проверку без контрпримера', () => {
    const verification = decodeVerification({
      ...verificationFixture,
      status: 'PROPERTY_HOLDS',
      counterexample: null,
      property_id: null,
      statistics: null,
      related_requirements: [],
      duration_ms: null,
      engine_version: null,
    })

    expect(verification.counterexample).toBeNull()
    expect(verification.statistics).toBeNull()
    expect(verification.property_id).toBeNull()
  })

  it('читает незавершённый прогон с пустыми счётчиками', () => {
    const verification = decodeVerification({
      ...verificationFixture,
      status: 'PENDING',
      statistics: null,
      counterexample: null,
      related_requirements: [],
      engine_version: null,
      duration_ms: null,
    })

    expect(verification.status).toBe('PENDING')
    expect(verification.related_requirements).toEqual([])
    expect(verification.statistics).toBeNull()
  })

  it('отвергает статус, которого нет в контракте', () => {
    expect(() => decodeVerification({ ...verificationFixture, status: 'ALL_GOOD' })).toThrow(
      DecodeError,
    )
  })

  it('читает статистику прогона', () => {
    const verification = decodeVerification(verificationFixture)

    expect(verification.statistics).toEqual({
      states_generated: 162,
      distinct_states: 37,
      depth: 8,
    })
  })

  it('читает цитату исходного требования', () => {
    const verification = decodeVerification(verificationFixture)

    expect(verification.related_requirements[0]?.paragraph_ref).toBe('p3')
  })
})

describe('decodeProfileSummary', () => {
  it('читает сводку профиля', () => {
    const summary = decodeProfileSummary({
      user: {
        id: 'u-1',
        email: 'analyst@example.com',
        display_name: 'Анна',
        created_at: '2026-08-31T23:47:00Z',
        last_login_at: '2026-10-12T23:47:00Z',
      },
      projects_count: 2,
      requirement_versions_count: 3,
      verification_count: 5,
      violation_count: 1,
      last_verification_at: '2026-10-16T09:12:00Z',
    })

    expect(summary.projects_count).toBe(2)
    expect(summary.violation_count).toBe(1)
    expect(summary.last_verification_at).toBe('2026-10-16T09:12:00Z')
  })

  it('принимает профиль без проверок', () => {
    const summary = decodeProfileSummary({
      user: {
        id: 'u-1',
        email: 'guest@example.com',
        display_name: null,
        created_at: '2026-08-31T23:47:00Z',
        last_login_at: null,
      },
      projects_count: 0,
      requirement_versions_count: 0,
      verification_count: 0,
      violation_count: 0,
      last_verification_at: null,
    })

    expect(summary.last_verification_at).toBeNull()
  })
})

describe('decodeApiErrorDetail', () => {
  it('читает контрактную ошибку с кодом', () => {
    const detail = decodeApiErrorDetail({
      detail: { code: 'INVALID_CREDENTIALS', message: 'Неверный email или пароль' },
    })

    expect(detail.code).toBe('INVALID_CREDENTIALS')
    expect(detail.message).toBe('Неверный email или пароль')
  })

  it('читает ошибку со строкой вместо объекта', () => {
    const detail = decodeApiErrorDetail({ detail: 'Поле name обязательно' })

    expect(detail.message).toBe('Поле name обязательно')
  })

  it('подставляет свой текст, если в объекте нет поля detail', () => {
    const detail = decodeApiErrorDetail({ unexpected: true })

    expect(detail.message).toBe('Запрос завершился ошибкой')
  })

  it('подставляет свой текст, если ответ вовсе не объект', () => {
    const detail = decodeApiErrorDetail('текст вместо json')

    expect(detail.message).toBe('Сервер вернул некорректный ответ')
  })

  it('подставляет свой текст, если в ошибке нет сообщения', () => {
    const detail = decodeApiErrorDetail({ detail: { code: 'TIMEOUT' } })

    expect(detail.code).toBe('TIMEOUT')
    expect(detail.message).toBe('Запрос завершился ошибкой')
  })
})
