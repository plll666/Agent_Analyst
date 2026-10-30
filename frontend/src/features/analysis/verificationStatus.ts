import { ROOT_CAUSES, VERIFICATION_STATUSES } from '../../types/api'
import type { PropertyType, Verification, VerificationStatus } from '../../types/api'

export type StatusTone = 'neutral' | 'bone' | 'success' | 'danger'

export interface VerificationStatusMeta {
  headline: string
  explanation: string
  shortLabel: string
  tone: StatusTone
  isPending: boolean
}

export const VERIFICATION_STATUS_META: Record<VerificationStatus, VerificationStatusMeta> = {
  [VERIFICATION_STATUSES.pending]: {
    headline: 'Идёт проверка',
    explanation:
      'Модель передана движку, идёт перебор состояний. Результат появится здесь сам — страницу обновлять не нужно.',
    shortLabel: 'Идёт',
    tone: 'neutral',
    isPending: true,
  },
  [VERIFICATION_STATUSES.propertyHolds]: {
    headline: 'Нарушений не найдено',
    explanation:
      'В исследованной модели заявленное правило нигде не нарушается: каждый найденный путь событий его соблюдает.',
    shortLabel: 'Нарушений нет',
    tone: 'success',
    isPending: false,
  },
  [VERIFICATION_STATUSES.propertyViolated]: {
    headline: 'Найдено нарушение',
    explanation:
      'Существует допустимая последовательность событий, которая ломает заявленное правило. Сценарий разобран ниже.',
    shortLabel: 'Нарушение',
    tone: 'danger',
    isPending: false,
  },
  [VERIFICATION_STATUSES.modelInvalid]: {
    headline: 'Проверка не выполнена',
    explanation:
      'Модель не прошла валидацию: часть переходов или свойств описана не так, чтобы её можно было перебрать.',
    shortLabel: 'Модель',
    tone: 'danger',
    isPending: false,
  },
  [VERIFICATION_STATUSES.timeout]: {
    headline: 'Проверка не завершилась',
    explanation:
      'Движок не успел обойти состояния за отведённое время. Ни нарушение, ни его отсутствие не установлены.',
    shortLabel: 'Таймаут',
    tone: 'danger',
    isPending: false,
  },
  [VERIFICATION_STATUSES.stateLimitReached]: {
    headline: 'Проверка не завершилась',
    explanation:
      'Достигнут лимит состояний: обход остановлен до конца. Ни нарушение, ни его отсутствие не установлены.',
    shortLabel: 'Лимит',
    tone: 'danger',
    isPending: false,
  },
  [VERIFICATION_STATUSES.engineError]: {
    headline: 'Движок завершился ошибкой',
    explanation:
      'Проверка не дала результата. Технические подробности — в технических деталях прогона.',
    shortLabel: 'Ошибка',
    tone: 'danger',
    isPending: false,
  },
  [VERIFICATION_STATUSES.agentError]: {
    headline: 'Агент не построил модель',
    explanation:
      'Агент не смог превратить требование в проверяемую модель, поэтому проверка не начиналась и вывод делать нельзя. Текст требования стоит переформулировать или дополнить.',
    shortLabel: 'Агент',
    tone: 'danger',
    isPending: false,
  },
}

/**
 * Особый исход: движок нашёл нарушение, но объяснение признало, что виновата
 * сама модель. Это не вывод о требовании, поэтому и заголовок другой.
 */
export const AGENT_MISREAD_META: VerificationStatusMeta = {
  headline: 'Модель ошибочна',
  explanation:
    'Контрпример относится к ошибке модели, а не к требованию: агент сам признал, что формула свойства не соответствует тексту. Это не вывод о системе — проверка недействительна, модель нужно перестроить.',
  shortLabel: 'Ошибка модели',
  tone: 'danger',
  isPending: false,
}

export function verificationMeta(
  verification: Pick<Verification, 'status' | 'root_cause'>,
): VerificationStatusMeta {
  if (
    verification.status === VERIFICATION_STATUSES.propertyViolated &&
    verification.root_cause === ROOT_CAUSES.agentError
  ) {
    return AGENT_MISREAD_META
  }

  return VERIFICATION_STATUS_META[verification.status]
}

export const PROPERTY_TYPE_LABELS: Record<PropertyType, string> = {
  invariant: 'Инвариант',
  forbidden_state: 'Запрещённое состояние',
  reachable: 'Достижимость',
  deadlock_free: 'Отсутствие тупиков',
}

export const HOLDS_EXPLANATION =
  'Важная оговорка: это не доказательство корректности системы. Проверены только те состояния, ' +
  'которые удалось построить по описанным правилам — если правила описаны неполно, проверка ' +
  'этого не заметит.'

export const INCONCLUSIVE_EXPLANATION =
  'Проверка не дала результата: это не значит ни «нарушения есть», ни «нарушений нет». ' +
  'Вывод делать нельзя — сначала нужно починить модель или поднять лимиты.'
