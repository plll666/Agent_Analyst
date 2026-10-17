export interface User {
  id: string
  email: string
  display_name: string | null
  created_at: string
  last_login_at: string | null
}

export interface Project {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface Requirement {
  id: string
  project_id: string
  version: number
  raw_text: string
  is_current: boolean
  created_at: string
}

export interface Collection<T> {
  items: T[]
}

export interface ApiErrorDetail {
  code: string
  message: string
}

export interface AuthCredentials {
  email: string
  password: string
}

export interface RegistrationPayload extends AuthCredentials {
  display_name: string | null
}

export interface ProjectPayload {
  name: string
  description: string | null
}

export interface ProjectPatch {
  name: string
  description: string | null
}

export interface RequirementPayload {
  raw_text: string
}

export const API_ERROR_CODES = {
  unauthenticated: 'UNAUTHENTICATED',
  invalidCredentials: 'INVALID_CREDENTIALS',
  emailTaken: 'EMAIL_TAKEN',
  notFound: 'NOT_FOUND',
  validation: 'VALIDATION_ERROR',
  malformedResponse: 'MALFORMED_RESPONSE',
} as const

export type ApiErrorCode = (typeof API_ERROR_CODES)[keyof typeof API_ERROR_CODES]

export const VARIABLE_TYPES = {
  enum: 'enum',
  boolean: 'boolean',
  integer: 'integer',
} as const

export type VariableType = (typeof VARIABLE_TYPES)[keyof typeof VARIABLE_TYPES]

export const PROPERTY_TYPES = {
  invariant: 'invariant',
  forbiddenState: 'forbidden_state',
  reachable: 'reachable',
  deadlockFree: 'deadlock_free',
} as const

export type PropertyType = (typeof PROPERTY_TYPES)[keyof typeof PROPERTY_TYPES]

export const MODEL_SOURCES = {
  agent: 'agent',
  manual: 'manual',
} as const

export type ModelSource = (typeof MODEL_SOURCES)[keyof typeof MODEL_SOURCES]

export const MODEL_VALIDATION_STATUSES = {
  valid: 'VALID',
  invalid: 'INVALID',
} as const

export type ModelValidationStatus =
  (typeof MODEL_VALIDATION_STATUSES)[keyof typeof MODEL_VALIDATION_STATUSES]

export const VERIFICATION_STATUSES = {
  pending: 'PENDING',
  propertyHolds: 'PROPERTY_HOLDS',
  propertyViolated: 'PROPERTY_VIOLATED',
  modelInvalid: 'MODEL_INVALID',
  timeout: 'TIMEOUT',
  stateLimitReached: 'STATE_LIMIT_REACHED',
  engineError: 'ENGINE_ERROR',
} as const

export type VerificationStatus = (typeof VERIFICATION_STATUSES)[keyof typeof VERIFICATION_STATUSES]

export const TERMINAL_VERIFICATION_STATUSES: VerificationStatus[] = [
  VERIFICATION_STATUSES.propertyHolds,
  VERIFICATION_STATUSES.propertyViolated,
  VERIFICATION_STATUSES.modelInvalid,
  VERIFICATION_STATUSES.timeout,
  VERIFICATION_STATUSES.stateLimitReached,
  VERIFICATION_STATUSES.engineError,
]

export type Literal = string | number | boolean | null

export interface ModelVariable {
  name: string
  type: VariableType
  values: string[]
  min: number | null
  max: number | null
}

export type ModelState = Record<string, Literal>

export interface VariableExpression {
  var: string
}

export interface EqualityExpression {
  eq: [Expression, Literal]
}

export interface MembershipExpression {
  in: [Expression, Literal[]]
}

export interface ConjunctionExpression {
  and: Expression[]
}

export type Expression =
  VariableExpression | EqualityExpression | MembershipExpression | ConjunctionExpression

export interface Effect {
  operator: string
  arguments: Literal[]
}

export interface ModelTransition {
  name: string
  guard: Expression | null
  effects: Effect[]
  source_reference: string | null
}

export interface ModelProperty {
  id: string
  type: PropertyType
  expression: Expression | null
  description: string | null
}

export interface BehavioralModel {
  variables: ModelVariable[]
  initial: ModelState
  transitions: ModelTransition[]
  properties: ModelProperty[]
}

export interface ModelVersion {
  id: string
  project_id: string
  version: number
  source: ModelSource
  schema_hash: string
  validation_status: ModelValidationStatus
  validation_errors: string[]
  document: BehavioralModel
  created_at: string
}

export interface VerificationStep {
  number: number
  transition: string | null
  state: ModelState
}

export interface VerificationCounterexample {
  steps: VerificationStep[]
}

export interface VerificationStatistics {
  states_generated: number
  distinct_states: number
  depth: number
}

export interface RelatedRequirement {
  paragraph_ref: string | null
  quote: string | null
}

export interface Verification {
  id: string
  project_id: string
  model_version_id: string
  property_id: string | null
  status: VerificationStatus
  engine: string
  engine_version: string | null
  statistics: VerificationStatistics | null
  counterexample: VerificationCounterexample | null
  related_requirements: RelatedRequirement[]
  duration_ms: number | null
  error_detail: string | null
  business_summary: string
  hypothesis: string | null
  question: string | null
  created_at: string
}

export interface ProfileSummary {
  user: User
  projects_count: number
  requirement_versions_count: number
  verification_count: number
  violation_count: number
  last_verification_at: string | null
}
