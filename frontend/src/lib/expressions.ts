import type { Effect, Expression, Literal, ModelState, ModelVariable } from '../types/api'

export const formatLiteral = (value: Literal): string => {
  if (value === null) {
    return '—'
  }

  if (typeof value === 'string') {
    return `"${value}"`
  }

  return String(value)
}

export const formatExpression = (expression: Expression): string => {
  if ('var' in expression) {
    return expression.var
  }

  if ('eq' in expression) {
    return `${formatExpression(expression.eq[0])} = ${formatLiteral(expression.eq[1])}`
  }

  if ('in' in expression) {
    const values = expression.in[1].map(formatLiteral).join(', ')

    return `${formatExpression(expression.in[0])} ∈ {${values}}`
  }

  return expression.and.map(formatExpression).join(' ∧ ')
}

export const formatEffect = (effect: Effect): string => {
  const [target, value] = effect.arguments

  if (effect.operator === 'set') {
    return `${String(target)} := ${formatLiteral(value ?? null)}`
  }

  return `${effect.operator}(${effect.arguments.map(formatLiteral).join(', ')})`
}

export const formatState = (state: ModelState): string =>
  Object.entries(state)
    .map(([name, value]) => `${name} = ${formatLiteral(value)}`)
    .join(', ')

export const formatDomain = (variable: ModelVariable): string => {
  if (variable.type === 'enum') {
    return variable.values.join(' | ')
  }

  if (variable.type === 'boolean') {
    return 'true | false'
  }

  if (variable.min !== null && variable.max !== null) {
    return `${variable.min}…${variable.max}`
  }

  return 'целые числа'
}
