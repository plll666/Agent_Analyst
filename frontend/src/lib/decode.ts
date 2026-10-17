import {
  API_ERROR_CODES,
  MODEL_VALIDATION_STATUSES,
  MODEL_SOURCES,
  PROPERTY_TYPES,
  VARIABLE_TYPES,
  VERIFICATION_STATUSES,
} from '../types/api'
import type {
  ApiErrorDetail,
  BehavioralModel,
  Effect,
  Expression,
  Literal,
  ModelProperty,
  ModelState,
  ModelTransition,
  ModelVariable,
  ModelVersion,
  ProfileSummary,
  Project,
  RelatedRequirement,
  Requirement,
  User,
  Verification,
  VerificationCounterexample,
  VerificationStatistics,
  VerificationStep,
  VariableType,
  PropertyType,
  VerificationStatus,
} from '../types/api'

export type Decoder<T> = (value: unknown) => T

export class DecodeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DecodeError'
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const readString = (source: Record<string, unknown>, key: string): string => {
  const value = source[key]

  if (typeof value !== 'string') {
    throw new DecodeError(`Ожидалась строка в поле «${key}»`)
  }

  return value
}

const readNullableString = (source: Record<string, unknown>, key: string): string | null => {
  const value = source[key]

  if (value === null || value === undefined) {
    return null
  }

  if (typeof value !== 'string') {
    throw new DecodeError(`Ожидалась строка или null в поле «${key}»`)
  }

  return value
}

const readNumber = (source: Record<string, unknown>, key: string): number => {
  const value = source[key]

  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new DecodeError(`Ожидалось число в поле «${key}»`)
  }

  return value
}

const readBoolean = (source: Record<string, unknown>, key: string): boolean => {
  const value = source[key]

  if (typeof value !== 'boolean') {
    throw new DecodeError(`Ожидалось true или false в поле «${key}»`)
  }

  return value
}

const readArray = (source: Record<string, unknown>, key: string): unknown[] => {
  const value = source[key]

  if (!Array.isArray(value)) {
    throw new DecodeError(`Ожидался список в поле «${key}»`)
  }

  return value
}

const expectRecord = (value: unknown): Record<string, unknown> => {
  if (!isRecord(value)) {
    throw new DecodeError('Ожидался JSON-объект')
  }

  return value
}

const expectArray = (value: unknown, label: string): unknown[] => {
  if (!Array.isArray(value)) {
    throw new DecodeError(`Ожидался список в «${label}»`)
  }

  return value
}

const readStringArray = (value: unknown[], label: string): string[] =>
  value.map((item) => {
    if (typeof item !== 'string') {
      throw new DecodeError(`Ожидались строки в списке «${label}»`)
    }

    return item
  })

export const decodeUser: Decoder<User> = (value) => {
  const source = expectRecord(value)

  return {
    id: readString(source, 'id'),
    email: readString(source, 'email'),
    display_name: readNullableString(source, 'display_name'),
    created_at: readString(source, 'created_at'),
    last_login_at: readNullableString(source, 'last_login_at'),
  }
}

export const decodeProject: Decoder<Project> = (value) => {
  const source = expectRecord(value)

  return {
    id: readString(source, 'id'),
    name: readString(source, 'name'),
    description: readNullableString(source, 'description'),
    created_at: readString(source, 'created_at'),
    updated_at: readString(source, 'updated_at'),
  }
}

export const decodeRequirement: Decoder<Requirement> = (value) => {
  const source = expectRecord(value)

  return {
    id: readString(source, 'id'),
    project_id: readString(source, 'project_id'),
    version: readNumber(source, 'version'),
    raw_text: readString(source, 'raw_text'),
    is_current: readBoolean(source, 'is_current'),
    created_at: readString(source, 'created_at'),
  }
}

const decodeLiteral = (value: unknown): Literal => {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return value
  }

  if (typeof value === 'number' && !Number.isNaN(value)) {
    return value
  }

  throw new DecodeError('Ожидалось строковое, числовое или булево значение')
}

const decodeLiteralArray = (value: unknown[]): Literal[] => value.map(decodeLiteral)

const decodeState = (value: unknown): ModelState => {
  const source = expectRecord(value)
  const state: ModelState = {}

  for (const [name, item] of Object.entries(source)) {
    state[name] = decodeLiteral(item)
  }

  return state
}

const decodeExpression = (value: unknown): Expression => {
  const source = expectRecord(value)

  if ('var' in source) {
    return { var: readString(source, 'var') }
  }

  if ('eq' in source) {
    const operands = readArray(source, 'eq')

    if (operands.length !== 2) {
      throw new DecodeError('В «eq» ожидались два операнда')
    }

    return { eq: [decodeExpression(operands[0]), decodeLiteral(operands[1])] }
  }

  if ('in' in source) {
    const operands = readArray(source, 'in')

    if (operands.length !== 2) {
      throw new DecodeError('В «in» ожидались операнд и список значений')
    }

    return {
      in: [decodeExpression(operands[0]), decodeLiteralArray(expectArray(operands[1], 'in'))],
    }
  }

  if ('and' in source) {
    return { and: readArray(source, 'and').map(decodeExpression) }
  }

  throw new DecodeError('Неизвестное выражение в модели')
}

const decodeOptionalExpression = (value: unknown): Expression | null =>
  value === null || value === undefined ? null : decodeExpression(value)

const decodeEffect = (value: unknown): Effect => {
  const source = expectRecord(value)
  const entries = Object.entries(source)
  const operator = entries.at(0)

  if (operator === undefined) {
    throw new DecodeError('Пустой эффект в модели')
  }

  return {
    operator: operator[0],
    arguments: decodeLiteralArray(
      operator[1] === undefined ? [] : expectArray(operator[1], operator[0]),
    ),
  }
}

const decodeVariable = (value: unknown): ModelVariable => {
  const source = expectRecord(value)
  const type = readString(source, 'type')

  if (!Object.values(VARIABLE_TYPES).includes(type as VariableType)) {
    throw new DecodeError(`Неизвестный тип переменной «${type}»`)
  }

  const min = source['min']
  const max = source['max']

  return {
    name: readString(source, 'name'),
    type: type as VariableType,
    values:
      source['values'] === undefined ? [] : readStringArray(readArray(source, 'values'), 'values'),
    min: typeof min === 'number' ? min : null,
    max: typeof max === 'number' ? max : null,
  }
}

const decodeTransition = (value: unknown): ModelTransition => {
  const source = expectRecord(value)

  return {
    name: readString(source, 'name'),
    guard: decodeOptionalExpression(source['guard']),
    effects: readArray(source, 'effects').map(decodeEffect),
    source_reference: readNullableString(source, 'source_reference'),
  }
}

const decodeProperty = (value: unknown): ModelProperty => {
  const source = expectRecord(value)
  const type = readString(source, 'type')

  if (!Object.values(PROPERTY_TYPES).includes(type as PropertyType)) {
    throw new DecodeError(`Неизвестный тип свойства «${type}»`)
  }

  return {
    id: readString(source, 'id'),
    type: type as PropertyType,
    expression: decodeOptionalExpression(source['expression']),
    description: readNullableString(source, 'description'),
  }
}

export const decodeBehavioralModel: Decoder<BehavioralModel> = (value) => {
  const source = expectRecord(value)

  return {
    variables: readArray(source, 'variables').map(decodeVariable),
    initial: decodeState(source['initial']),
    transitions: readArray(source, 'transitions').map(decodeTransition),
    properties: readArray(source, 'properties').map(decodeProperty),
  }
}

export const decodeModelVersion: Decoder<ModelVersion> = (value) => {
  const source = expectRecord(value)
  const source_ = readString(source, 'source')
  const validationStatus = readString(source, 'validation_status')

  if (!Object.values(MODEL_SOURCES).includes(source_ as ModelVersion['source'])) {
    throw new DecodeError(`Неизвестный источник модели «${source_}»`)
  }

  if (
    !Object.values(MODEL_VALIDATION_STATUSES).includes(
      validationStatus as ModelVersion['validation_status'],
    )
  ) {
    throw new DecodeError(`Неизвестный статус валидации «${validationStatus}»`)
  }

  const validationErrors = source['validation_errors']

  return {
    id: readString(source, 'id'),
    project_id: readString(source, 'project_id'),
    version: readNumber(source, 'version'),
    source: source_ as ModelVersion['source'],
    schema_hash: readString(source, 'schema_hash'),
    validation_status: validationStatus as ModelVersion['validation_status'],
    validation_errors:
      validationErrors === null || validationErrors === undefined
        ? []
        : readStringArray(
            Array.isArray(validationErrors) ? validationErrors : [],
            'validation_errors',
          ),
    document: decodeBehavioralModel(source['document']),
    created_at: readString(source, 'created_at'),
  }
}

const decodeVerificationStep = (value: unknown): VerificationStep => {
  const source = expectRecord(value)

  return {
    number: readNumber(source, 'number'),
    transition: readNullableString(source, 'transition'),
    state: decodeState(source['state']),
  }
}

const decodeCounterexample = (value: unknown): VerificationCounterexample => {
  const source = expectRecord(value)

  return { steps: readArray(source, 'steps').map(decodeVerificationStep) }
}

const decodeStatistics = (value: unknown): VerificationStatistics => {
  const source = expectRecord(value)

  return {
    states_generated: readNumber(source, 'states_generated'),
    distinct_states: readNumber(source, 'distinct_states'),
    depth: readNumber(source, 'depth'),
  }
}

const decodeRelatedRequirement = (value: unknown): RelatedRequirement => {
  const source = expectRecord(value)

  return {
    paragraph_ref: readNullableString(source, 'paragraph_ref'),
    quote: readNullableString(source, 'quote'),
  }
}

export const decodeVerification: Decoder<Verification> = (value) => {
  const source = expectRecord(value)
  const status = readString(source, 'status')

  if (!Object.values(VERIFICATION_STATUSES).includes(status as VerificationStatus)) {
    throw new DecodeError(`Неизвестный статус проверки «${status}»`)
  }

  const statistics = source['statistics']
  const counterexample = source['counterexample']
  const relatedRequirements = source['related_requirements']
  const duration = source['duration_ms']

  return {
    id: readString(source, 'id'),
    project_id: readString(source, 'project_id'),
    model_version_id: readString(source, 'model_version_id'),
    property_id: readNullableString(source, 'property_id'),
    status: status as VerificationStatus,
    engine: readString(source, 'engine'),
    engine_version: readNullableString(source, 'engine_version'),
    statistics:
      statistics === null || statistics === undefined ? null : decodeStatistics(statistics),
    counterexample:
      counterexample === null || counterexample === undefined
        ? null
        : decodeCounterexample(counterexample),
    related_requirements:
      relatedRequirements === null || relatedRequirements === undefined
        ? []
        : (Array.isArray(relatedRequirements) ? relatedRequirements : []).map(
            decodeRelatedRequirement,
          ),
    duration_ms: typeof duration === 'number' ? duration : null,
    error_detail: readNullableString(source, 'error_detail'),
    business_summary:
      typeof source['business_summary'] === 'string' ? source['business_summary'] : '',
    hypothesis: readNullableString(source, 'hypothesis'),
    question: readNullableString(source, 'question'),
    created_at: readString(source, 'created_at'),
  }
}

export const decodeProfileSummary: Decoder<ProfileSummary> = (value) => {
  const source = expectRecord(value)

  return {
    user: decodeUser(source['user']),
    projects_count: readNumber(source, 'projects_count'),
    requirement_versions_count: readNumber(source, 'requirement_versions_count'),
    verification_count: readNumber(source, 'verification_count'),
    violation_count: readNumber(source, 'violation_count'),
    last_verification_at: readNullableString(source, 'last_verification_at'),
  }
}

export const decodeCollection =
  <T>(decodeItem: Decoder<T>): Decoder<T[]> =>
  (value) => {
    const source = expectRecord(value)
    const items = source['items']

    if (!Array.isArray(items)) {
      throw new DecodeError('Ожидался список в поле «items»')
    }

    return items.map(decodeItem)
  }

export const decodeVoid: Decoder<undefined> = () => undefined

export const decodeApiErrorDetail: Decoder<ApiErrorDetail> = (value) => {
  if (!isRecord(value)) {
    return {
      code: API_ERROR_CODES.validation,
      message: 'Сервер вернул некорректный ответ',
    }
  }

  const detail = value['detail']

  if (typeof detail === 'string') {
    return { code: API_ERROR_CODES.validation, message: detail }
  }

  if (isRecord(detail)) {
    const code = detail['code']
    const message = detail['message']

    return {
      code: typeof code === 'string' ? code : API_ERROR_CODES.validation,
      message: typeof message === 'string' ? message : 'Запрос завершился ошибкой',
    }
  }

  return { code: API_ERROR_CODES.validation, message: 'Запрос завершился ошибкой' }
}
