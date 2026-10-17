import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { gsap } from 'gsap'
import { useGSAP } from '@gsap/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { VERIFICATION_STATUSES } from '../../types/api'
import type { Verification } from '../../types/api'
import { VerificationOutcome } from './VerificationOutcome'

beforeAll(() => {
  gsap.registerPlugin(useGSAP)
  vi.stubGlobal(
    'matchMedia',
    (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  )
})

const violatedVerification: Verification = {
  id: 'run-1',
  project_id: 'project-1',
  model_version_id: 'model-1',
  property_id: 'P2',
  status: VERIFICATION_STATUSES.propertyViolated,
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
  related_requirements: [],
  duration_ms: 812,
  error_detail: null,
  business_summary: 'Заявка создана.\nЗаявка согласована.',
  hypothesis: null,
  question: null,
  created_at: '2026-10-16T09:12:00Z',
}

const makeVerification = (overrides: Partial<Verification>): Verification => ({
  ...violatedVerification,
  counterexample: null,
  statistics: null,
  duration_ms: null,
  related_requirements: [],
  hypothesis: null,
  question: null,
  ...overrides,
})

const renderOutcome = (verification: Verification): ReturnType<typeof render> =>
  render(
    <VerificationOutcome
      verification={verification}
      isDetailsOpen={false}
      onToggleDetails={vi.fn()}
    />,
  )

describe('VerificationOutcome: успешная проверка', () => {
  it('показывает заголовок об отсутствии нарушений', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyHolds,
        business_summary: 'Отменённую заявку исполнить больше нельзя.',
      }),
    )

    expect(screen.getByRole('heading', { name: 'Нарушений не найдено' })).toBeInTheDocument()
  })

  it('печатает сценарий по шагам', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyHolds,
        business_summary: 'Первый шаг.\nВторой шаг.\nТретий шаг.',
      }),
    )

    const scenario = screen.getByRole('heading', { name: 'Что произошло' }).parentElement

    expect(scenario).not.toBeNull()
    expect(within(scenario as HTMLElement).getByText('Первый шаг.')).toBeInTheDocument()
    expect(within(scenario as HTMLElement).getByText('Второй шаг.')).toBeInTheDocument()
    expect(within(scenario as HTMLElement).getByText('Третий шаг.')).toBeInTheDocument()
  })

  it('добавляет оговорку, что это не доказательство корректности', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyHolds,
        business_summary: 'Нарушений нет.',
      }),
    )

    expect(screen.getByText(/это не доказательство корректности/i)).toBeInTheDocument()
  })
})

describe('VerificationOutcome: проверка без результата', () => {
  it.each([
    ['таймаут', VERIFICATION_STATUSES.timeout],
    ['лимит состояний', VERIFICATION_STATUSES.stateLimitReached],
  ])('показывает %s как «проверка не завершилась», а не как успех', (_label, status) => {
    renderOutcome(
      makeVerification({
        status,
        business_summary: 'Проверка не дала результата.',
      }),
    )

    expect(screen.getByRole('heading', { name: 'Проверка не завершилась' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Нарушений не найдено' })).not.toBeInTheDocument()
    expect(screen.getByText(/Вывод делать нельзя/)).toBeInTheDocument()
  })

  it('объясняет, что результат не установлен', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.timeout,
        business_summary: 'Движок не успел.',
      }),
    )

    expect(screen.getByText(/Ни нарушение, ни его отсутствие не установлены/)).toBeInTheDocument()
  })

  it('не показывает оговорку про доказательство, если успеха не было', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.stateLimitReached,
        business_summary: 'Обход остановлен.',
      }),
    )

    expect(screen.queryByText(/не доказательство корректности/i)).not.toBeInTheDocument()
  })
})

describe('VerificationOutcome: контрпример по шагам', () => {
  it('показывает цепочку переходов', () => {
    renderOutcome(violatedVerification)

    expect(screen.getByRole('heading', { name: 'Цепочка событий' })).toBeInTheDocument()
    expect(screen.getByText('Approve')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Execute')).toBeInTheDocument()
  })

  it('держит состояния свёрнутыми до нажатия', () => {
    renderOutcome(violatedVerification)

    expect(screen.queryByText(/status = "Executed"/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Показать состояния по шагам/ })).toBeInTheDocument()
  })

  it('раскрывает состояния по шагам с номером и переходом', async () => {
    const user = userEvent.setup()
    renderOutcome(violatedVerification)

    await user.click(screen.getByRole('button', { name: /Показать состояния по шагам/ }))

    const revealed = document.querySelector('.reveal-steps')
    expect(revealed).not.toBeNull()

    const steps = within(revealed as HTMLElement).getAllByRole('listitem')
    expect(steps).toHaveLength(4)
    expect(screen.getByText('старт')).toBeInTheDocument()
    expect(screen.getByText('шаг 1')).toBeInTheDocument()
    expect(screen.getByText('шаг 3')).toBeInTheDocument()
    expect(
      screen.getByText(/status = "Executed", approved = true, cancelled = true/),
    ).toBeInTheDocument()
  })

  it('выделяет нарушающее состояние последнего шага', async () => {
    const user = userEvent.setup()
    renderOutcome(violatedVerification)

    await user.click(screen.getByRole('button', { name: /Показать состояния по шагам/ }))

    const violating = screen.getByText(/status = "Executed"/)

    expect(violating).toHaveClass('text-danger')
  })

  it('меняет подпись кнопки при раскрытии', async () => {
    const user = userEvent.setup()
    renderOutcome(violatedVerification)

    const toggle = screen.getByRole('button', { name: /Показать состояния по шагам/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(screen.getByRole('button', { name: /Скрыть состояния по шагам/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('не показывает кнопку шагов, если контрпримера нет', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyHolds,
        business_summary: 'Нарушений нет.',
      }),
    )

    expect(screen.queryByRole('button', { name: /состояния по шагам/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Цепочка событий' })).not.toBeInTheDocument()
  })
})

describe('VerificationOutcome: пояснения агента', () => {
  it('показывает гипотезу и вопрос отдельными блоками', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyViolated,
        counterexample: violatedVerification.counterexample,
        business_summary: 'Заявка согласована.',
        hypothesis: 'Нет условия, запрещающего Execute после Cancel',
        question: 'Должен ли Cancel снимать признак согласования?',
      }),
    )

    expect(screen.getByRole('heading', { name: 'Что, скорее всего, не так' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Что нужно уточнить' })).toBeInTheDocument()
  })

  it('скрывает блоки, если агент ничего не предположил', () => {
    renderOutcome(
      makeVerification({
        status: VERIFICATION_STATUSES.propertyHolds,
        business_summary: 'Нарушений нет.',
      }),
    )

    expect(
      screen.queryByRole('heading', { name: 'Что, скорее всего, не так' }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Что нужно уточнить' })).not.toBeInTheDocument()
  })
})
