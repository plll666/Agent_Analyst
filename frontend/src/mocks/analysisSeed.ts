import type {
  Literal,
  PropertyType,
  RelatedRequirement,
  VariableType,
  VerificationCounterexample,
  VerificationStatistics,
  VerificationStatus,
} from '../types/api'

interface MockVariable {
  name: string
  type: VariableType
  values?: string[]
  min?: number
  max?: number
}

interface MockTransition {
  name: string
  guard: unknown
  effects: Record<string, unknown>[]
  source_reference: string | null
}

interface MockProperty {
  id: string
  type: PropertyType
  expression: unknown
  description: string | null
}

interface MockModelDocument {
  variables: MockVariable[]
  initial: Record<string, Literal>
  transitions: MockTransition[]
  properties: MockProperty[]
}

export interface MockModelRecord {
  id: string
  projectId: string
  version: number
  source: 'agent' | 'manual'
  schemaHash: string
  validationStatus: 'VALID' | 'INVALID'
  validationErrors: string[]
  document: MockModelDocument
  outcome: VerificationStatus
  createdAt: string
}

export interface MockVerificationRecord {
  id: string
  projectId: string
  modelVersionId: string
  propertyId: string | null
  status: VerificationStatus
  engine: string
  engineVersion: string | null
  statistics: VerificationStatistics | null
  counterexample: VerificationCounterexample | null
  relatedRequirements: RelatedRequirement[]
  durationMs: number | null
  errorDetail: string | null
  businessSummary: string
  hypothesis: string | null
  question: string | null
  createdAt: string
  startedAt: number | null
}

export const MOCK_RUN_DURATION_MS = 5200

export const MOCK_PROJECT_IDS = {
  orders: '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c901',
  limits: '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c902',
  contracts: '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c903',
} as const

const ORDERS_MODEL_V1_ID = '5d1a8e42-9b7c-4f31-8e05-2c6b9a4d7f01'
const ORDERS_MODEL_V2_ID = '5d1a8e42-9b7c-4f31-8e05-2c6b9a4d7f02'
const CONTRACTS_MODEL_ID = '5d1a8e42-9b7c-4f31-8e05-2c6b9a4d7f03'

const ORDERS_RUN_V1_ID = '9f4b2c77-3a15-4d68-b0e9-71c5d8a2f601'
const ORDERS_RUN_V2_ID = '9f4b2c77-3a15-4d68-b0e9-71c5d8a2f602'
const CONTRACTS_RUN_ID = '9f4b2c77-3a15-4d68-b0e9-71c5d8a2f603'

const daysAgo = (days: number, hours = 0): string =>
  new Date(Date.now() - days * 86_400_000 - hours * 3_600_000).toISOString()

const ordersModelV1: MockModelDocument = {
  variables: [
    { name: 'status', type: 'enum', values: ['Created', 'Approved', 'Cancelled', 'Executed'] },
    { name: 'approved', type: 'boolean' },
    { name: 'cancelled', type: 'boolean' },
    { name: 'attempts', type: 'integer', min: 0, max: 3 },
  ],
  initial: { status: 'Created', approved: false, cancelled: false, attempts: 0 },
  transitions: [
    {
      name: 'Approve',
      guard: { eq: [{ var: 'status' }, 'Created'] },
      effects: [{ set: ['status', 'Approved'] }, { set: ['approved', true] }],
      source_reference: 'p3',
    },
    {
      name: 'Cancel',
      guard: { in: [{ var: 'status' }, ['Created', 'Approved']] },
      effects: [{ set: ['status', 'Cancelled'] }, { set: ['cancelled', true] }],
      source_reference: 'p5',
    },
    {
      name: 'Execute',
      guard: { eq: [{ var: 'approved' }, true] },
      effects: [{ set: ['status', 'Executed'] }],
      source_reference: 'p6',
    },
  ],
  properties: [
    {
      id: 'P1',
      type: 'invariant',
      expression: {
        and: [{ eq: [{ var: 'status' }, 'Executed'] }, { eq: [{ var: 'cancelled' }, false] }],
      },
      description: 'Исполненная заявка не может быть отменённой',
    },
    {
      id: 'P2',
      type: 'forbidden_state',
      expression: {
        and: [{ eq: [{ var: 'status' }, 'Executed'] }, { eq: [{ var: 'cancelled' }, true] }],
      },
      description: 'Отменённую заявку исполнять нельзя',
    },
    {
      id: 'P3',
      type: 'reachable',
      expression: { eq: [{ var: 'status' }, 'Executed'] },
      description: 'Исполненная заявка должна быть достижима',
    },
    {
      id: 'P4',
      type: 'deadlock_free',
      expression: null,
      description: 'Из каждого достижимого состояния есть разрешённый переход',
    },
  ],
}

const ordersModelV2: MockModelDocument = {
  ...ordersModelV1,
  transitions: ordersModelV1.transitions.map((transition) => {
    if (transition.name === 'Cancel') {
      return {
        ...transition,
        effects: [...transition.effects, { set: ['approved', false] }],
      }
    }

    if (transition.name === 'Execute') {
      return {
        ...transition,
        guard: {
          and: [{ eq: [{ var: 'approved' }, true] }, { eq: [{ var: 'status' }, 'Approved'] }],
        },
      }
    }

    return transition
  }),
}

const contractsModel: MockModelDocument = {
  variables: [
    {
      name: 'stage',
      type: 'enum',
      values: ['Draft', 'Legal', 'Finance', 'Approved', 'Rejected'],
    },
    { name: 'legalApproved', type: 'boolean' },
  ],
  initial: { stage: 'Draft', legalApproved: false, financeApproved: false },
  transitions: [
    {
      name: 'SendToLegal',
      guard: { eq: [{ var: 'stage' }, 'Draft'] },
      effects: [{ set: ['stage', 'Legal'] }],
      source_reference: 'p2',
    },
    {
      name: 'LegalApprove',
      guard: { eq: [{ var: 'stage' }, 'Legal'] },
      effects: [{ set: ['stage', 'Finance'] }, { set: ['legalApproved', true] }],
      source_reference: 'p3',
    },
    {
      name: 'FinanceApprove',
      guard: { eq: [{ var: 'stage' }, 'Finance'] },
      effects: [{ set: ['stage', 'Approved'] }],
      source_reference: 'p4',
    },
    {
      name: 'FinanceReject',
      guard: { eq: [{ var: 'stage' }, 'Finance'] },
      effects: [{ set: ['stage', 'Rejected'] }],
      source_reference: 'p4',
    },
    {
      name: 'Revise',
      guard: { eq: [{ var: 'stage' }, 'Rejected'] },
      effects: [{ set: ['stage', 'Legal'] }],
      source_reference: 'p6',
    },
  ],
  properties: [
    {
      id: 'P1',
      type: 'invariant',
      expression: {
        and: [{ eq: [{ var: 'stage' }, 'Approved'] }, { eq: [{ var: 'legalApproved' }, true] }],
      },
      description: 'Утверждён договор прошёл юридическую проверку',
    },
    {
      id: 'P2',
      type: 'deadlock_free',
      expression: null,
      description: 'Из любой стадии есть путь дальше',
    },
  ],
}

export const buildSeedModels = (): MockModelRecord[] => [
  {
    id: ORDERS_MODEL_V1_ID,
    projectId: MOCK_PROJECT_IDS.orders,
    version: 1,
    source: 'agent',
    schemaHash: 'c0ffee4a1b7d93e2a6f5c84d0b71e3a92c4f8d1e60b7a35c9e2d4f8a1b6c30d95',
    validationStatus: 'VALID',
    validationErrors: [],
    document: ordersModelV1,
    outcome: 'PROPERTY_VIOLATED',
    createdAt: daysAgo(20),
  },
  {
    id: ORDERS_MODEL_V2_ID,
    projectId: MOCK_PROJECT_IDS.orders,
    version: 2,
    source: 'agent',
    schemaHash: 'b19a7d3f5c2e8a40d7b6f1e93c5a8d204e7b3f6a1c9d82e5b4a70f3c6d9e2b18',
    validationStatus: 'VALID',
    validationErrors: [],
    document: ordersModelV2,
    outcome: 'PROPERTY_HOLDS',
    createdAt: daysAgo(1, 3),
  },
  {
    id: CONTRACTS_MODEL_ID,
    projectId: MOCK_PROJECT_IDS.contracts,
    version: 1,
    source: 'agent',
    schemaHash: 'a71f4c9e2d6b80a35f1c7e94b2d0a68f5e3c1b97d4a20f6e8c5b3a1d9f7e4c26',
    validationStatus: 'VALID',
    validationErrors: [],
    document: contractsModel,
    outcome: 'PROPERTY_HOLDS',
    createdAt: daysAgo(5),
  },
]

const violatedCounterexample: VerificationCounterexample = {
  steps: [
    {
      number: 0,
      transition: null,
      state: { status: 'Created', approved: false, cancelled: false, attempts: 0 },
    },
    {
      number: 1,
      transition: 'Approve',
      state: { status: 'Approved', approved: true, cancelled: false, attempts: 0 },
    },
    {
      number: 2,
      transition: 'Cancel',
      state: { status: 'Cancelled', approved: true, cancelled: true, attempts: 0 },
    },
    {
      number: 3,
      transition: 'Execute',
      state: { status: 'Executed', approved: true, cancelled: true, attempts: 0 },
    },
  ],
}

const violatedSummary = [
  'Менеджер создал заявку — она ждёт согласования.',
  'Менеджер согласовал заявку: признак approved стал true.',
  'Пользователь отменил заявку, но признак approved остался true.',
  'После отмены заявку всё равно удалось исполнить — Execute проверяет только approved, а не текущий статус.',
].join('\n')

const holdsSummary = [
  'Отменённую заявку исполнить больше нельзя.',
  'Переход Cancel теперь сбрасывает признак approved, а Execute дополнительно требует статус Approved.',
  'Запрещённое состояние status = Executed при cancelled = true недостижимо во всех исследованных состояниях.',
].join('\n')

export const buildSeedVerifications = (): MockVerificationRecord[] => [
  {
    id: ORDERS_RUN_V1_ID,
    projectId: MOCK_PROJECT_IDS.orders,
    modelVersionId: ORDERS_MODEL_V1_ID,
    propertyId: 'P2',
    status: 'PROPERTY_VIOLATED',
    engine: 'TLC',
    engineVersion: '1.7.4',
    statistics: { states_generated: 162, distinct_states: 37, depth: 8 },
    counterexample: violatedCounterexample,
    relatedRequirements: [
      {
        paragraph_ref: 'p3',
        quote:
          'Заявка после согласования может быть исполнена. Пользователь может отменить заявку до исполнения.',
      },
    ],
    durationMs: 812,
    errorDetail: null,
    businessSummary: violatedSummary,
    hypothesis:
      'В модели отсутствует условие, запрещающее Execute после Cancel, либо Cancel должен сбрасывать признак approved.',
    question:
      'Отмена заявки должна снимать признак approved, или запрет исполнения должен быть отдельным условием в переходе Execute?',
    createdAt: daysAgo(20),
    startedAt: null,
  },
  {
    id: ORDERS_RUN_V2_ID,
    projectId: MOCK_PROJECT_IDS.orders,
    modelVersionId: ORDERS_MODEL_V2_ID,
    propertyId: 'P2',
    status: 'PROPERTY_HOLDS',
    engine: 'TLC',
    engineVersion: '1.7.4',
    statistics: { states_generated: 148, distinct_states: 31, depth: 7 },
    counterexample: null,
    relatedRequirements: [],
    durationMs: 640,
    errorDetail: null,
    businessSummary: holdsSummary,
    hypothesis: null,
    question: null,
    createdAt: daysAgo(1, 3),
    startedAt: null,
  },
  {
    id: CONTRACTS_RUN_ID,
    projectId: MOCK_PROJECT_IDS.contracts,
    modelVersionId: CONTRACTS_MODEL_ID,
    propertyId: 'P1',
    status: 'PROPERTY_HOLDS',
    engine: 'TLC',
    engineVersion: '1.7.4',
    statistics: { states_generated: 74, distinct_states: 12, depth: 5 },
    counterexample: null,
    relatedRequirements: [],
    durationMs: 310,
    errorDetail: null,
    businessSummary:
      'Утвердить договор можно только после юридической проверки — иначе состояние недостижимо.',
    hypothesis: null,
    question: null,
    createdAt: daysAgo(5),
    startedAt: null,
  },
]

export const outcomeFor = (
  status: VerificationStatus,
  model: MockModelRecord,
): Pick<
  MockVerificationRecord,
  | 'propertyId'
  | 'statistics'
  | 'counterexample'
  | 'relatedRequirements'
  | 'businessSummary'
  | 'hypothesis'
  | 'question'
> => {
  if (status === 'PROPERTY_VIOLATED') {
    return {
      propertyId: 'P2',
      statistics: { states_generated: 162, distinct_states: 37, depth: 8 },
      counterexample: violatedCounterexample,
      relatedRequirements: [
        {
          paragraph_ref: 'p3',
          quote:
            'Заявка после согласования может быть исполнена. Пользователь может отменить заявку до исполнения.',
        },
      ],
      businessSummary: violatedSummary,
      hypothesis:
        'В модели отсутствует условие, запрещающее Execute после Cancel, либо Cancel должен сбрасывать признак approved.',
      question:
        'Отмена заявки должна снимать признак approved, или запрет исполнения должен быть отдельным условием в переходе Execute?',
    }
  }

  if (status === 'PROPERTY_HOLDS') {
    return {
      propertyId: 'P2',
      statistics: { states_generated: 148, distinct_states: 31, depth: 7 },
      counterexample: null,
      relatedRequirements: [],
      businessSummary: holdsSummary,
      hypothesis: null,
      question: null,
    }
  }

  if (status === 'TIMEOUT' || status === 'STATE_LIMIT_REACHED') {
    return {
      propertyId: 'P2',
      statistics: { states_generated: 120_000, distinct_states: 41_208, depth: 37 },
      counterexample: null,
      relatedRequirements: [],
      businessSummary:
        'Перебор остановлен до полного обхода состояний. Ни нарушение, ни его отсутствие не установлены.',
      hypothesis: null,
      question: null,
    }
  }

  return {
    propertyId: null,
    statistics: null,
    counterexample: null,
    relatedRequirements: [],
    businessSummary: `Проверка не выполнена: модель v${model.version} не прошла подготовку к прогону.`,
    hypothesis: null,
    question: null,
  }
}
