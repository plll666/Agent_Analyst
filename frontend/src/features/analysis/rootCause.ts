import { ROOT_CAUSES } from '../../types/api'
import type { RootCause } from '../../types/api'

export interface RootCauseMeta {
  label: string
  description: string
  className: string
}

/**
 * Три класса причины из кейса. Подпись отвечает на вопрос «кто виноват», а
 * описание — «что с этим делать»: править требование, править интерпретацию или
 * дописывать отсутствующее правило.
 */
export const ROOT_CAUSE_META: Record<RootCause, RootCauseMeta> = {
  [ROOT_CAUSES.requirementError]: {
    label: 'Ошибка в требовании',
    description:
      'Модель верно отразила текст, но сам текст допускает такой сценарий. Правило нужно уточнить в требовании.',
    className: 'border-bone/40 bg-bone-soft/40 text-bone',
  },
  [ROOT_CAUSES.agentError]: {
    label: 'Ошибка агента',
    description:
      'Модель расходится с текстом: условие перехода или эффект не соответствует написанному. Это ошибка интерпретации, а не требования.',
    className: 'border-danger/30 bg-surface-danger text-danger',
  },
  [ROOT_CAUSES.missingRule]: {
    label: 'Нет правила',
    description:
      'В тексте нет правила для этого случая. Нужно решить, как система должна себя вести, и дописать требование.',
    className: 'border-line-strong bg-raised/40 text-muted',
  },
}
