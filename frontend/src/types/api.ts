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
  source_import_id?: string | null
  source_modified?: boolean
  fragments?: RequirementFragment[]
}

export interface RequirementFragment {
  id: string
  kind: 'paragraph' | 'table_cell'
  start: number
  end: number
  source_locator: string | null
}

export interface RequirementImport {
  id: string
  project_id: string
  filename: string
  format: 'txt' | 'docx'
  size_bytes: number
  sha256: string
  raw_text: string
  fragments: RequirementFragment[]
  warnings: { code: string; message: string }[]
  created_at: string
}

export interface RequirementImportCapabilities {
  formats: ('txt' | 'docx')[]
  max_file_bytes: number
  max_text_chars: number
  txt_encoding: string
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
  source_import_id?: string | null
}

export const API_ERROR_CODES = {
  unauthenticated: 'UNAUTHENTICATED',
  invalidCredentials: 'INVALID_CREDENTIALS',
  emailTaken: 'EMAIL_TAKEN',
  notFound: 'NOT_FOUND',
  validation: 'VALIDATION_ERROR',
  malformedResponse: 'MALFORMED_RESPONSE',
  llmUnavailable: 'LLM_UNAVAILABLE',
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
  agentError: 'AGENT_ERROR',
  cancelled: 'CANCELLED',
} as const

export type VerificationStatus = (typeof VERIFICATION_STATUSES)[keyof typeof VERIFICATION_STATUSES]

export const TERMINAL_VERIFICATION_STATUSES: VerificationStatus[] = [
  VERIFICATION_STATUSES.propertyHolds,
  VERIFICATION_STATUSES.propertyViolated,
  VERIFICATION_STATUSES.modelInvalid,
  VERIFICATION_STATUSES.timeout,
  VERIFICATION_STATUSES.stateLimitReached,
  VERIFICATION_STATUSES.engineError,
  VERIFICATION_STATUSES.agentError,
  VERIFICATION_STATUSES.cancelled,
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
  requirement_id: string | null
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

export const ROOT_CAUSES = {
  requirementError: 'REQUIREMENT_ERROR',
  agentError: 'AGENT_ERROR',
  missingRule: 'MISSING_RULE',
} as const

export type RootCause = (typeof ROOT_CAUSES)[keyof typeof ROOT_CAUSES]

export interface RelatedRequirement {
  paragraph_ref: string | null
  quote: string | null
  requirement_id?: string | null
  start?: number | null
  end?: number | null
}

export type ExecutionStatus =
  'QUEUED' | 'RUNNING' | 'CANCELLING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export type StageState = 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'SKIPPED'

export interface AnalysisStage {
  stage_id: string
  parent_stage_id: string | null
  scope: 'agent' | 'core'
  name: string
  state: StageState
  build_index: number | null
  attempt: number
  property_id: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  reason_code: string | null
  message: string | null
  statistics: VerificationStatistics | null
}

export interface AnalysisEvent {
  schema_version: number
  verification_id: string
  seq: number
  occurred_at: string
  type: 'run.updated' | 'stage.updated' | 'stage.statistics' | 'agent.rebuild' | 'run.finished'
  data: Record<string, unknown>
}

export interface AnalysisEventPage {
  items: AnalysisEvent[]
  next_after_seq: number
  has_more: boolean
}

export type SubmissionMode = 'CREATED' | 'REUSED' | 'IN_PROGRESS'

export interface Verification {
  id: string
  project_id: string
  model_version_id: string | null
  requirement_id: string | null
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
  root_cause: RootCause | null
  /** Выбор пользователя: рассуждала ли модель; null — режим не выбирали. */
  reasoning?: boolean | null
  created_at: string
  execution_status?: ExecutionStatus
  input_key?: string
  started_at?: string | null
  finished_at?: string | null
  last_event_seq?: number
  active_stages?: AnalysisStage[]
}

export interface LlmCapabilities {
  model: string
  reasoning: {
    available: boolean | null
    always_on: boolean
    source: string
    detail: string | null
  }
}

export interface ProfileSummary {
  user: User
  projects_count: number
  requirement_versions_count: number
  verification_count: number
  violation_count: number
  last_verification_at: string | null
}
