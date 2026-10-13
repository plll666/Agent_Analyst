import type { VerificationStatus } from '../types/api'
import {
  MOCK_RUN_DURATION_MS,
  buildSeedModels,
  buildSeedVerifications,
  outcomeFor,
} from './analysisSeed'
import type { MockModelRecord, MockVerificationRecord } from './analysisSeed'

export interface MockUserRecord {
  id: string
  email: string
  password: string
  displayName: string | null
  createdAt: string
  lastLoginAt: string | null
}

export interface MockProjectRecord {
  id: string
  ownerId: string
  name: string
  description: string | null
  createdAt: string
  updatedAt: string
}

export interface MockRequirementRecord {
  id: string
  projectId: string
  version: number
  rawText: string
  isCurrent: boolean
  createdAt: string
}

interface MockSessionRecord {
  token: string
  userId: string
  expiresAt: number
}

export interface ProfileSummaryRecord {
  user: MockUserRecord
  projectsCount: number
  requirementVersionsCount: number
  verificationCount: number
  violationCount: number
  lastVerificationAt: string | null
}

interface MockDatabase {
  schemaVersion: number
  users: MockUserRecord[]
  projects: MockProjectRecord[]
  requirements: MockRequirementRecord[]
  models: MockModelRecord[]
  verifications: MockVerificationRecord[]
  sessions: MockSessionRecord[]
  fallbackToken: string | null
}

export { MOCK_RUN_DURATION_MS }
export type { MockModelRecord, MockVerificationRecord }

const STORAGE_KEY = 'agent-analyst-mock-db'
const MOCK_SCHEMA_VERSION = 2

const ANALYST_ID = '0d7c1f6a-6d3f-4f0b-9a11-3b1a5c2d7e01'
const GUEST_ID = '0d7c1f6a-6d3f-4f0b-9a11-3b1a5c2d7e02'

const ORDERS_PROJECT_ID = '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c901'
const LIMITS_PROJECT_ID = '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c902'
const CONTRACTS_PROJECT_ID = '2c6e9a10-51c7-4b4d-9f0a-71d2b4e5c903'

const daysAgo = (days: number, hours = 0): string =>
  new Date(Date.now() - days * 86_400_000 - hours * 3_600_000).toISOString()

const seedDatabase = (): MockDatabase => ({
  schemaVersion: MOCK_SCHEMA_VERSION,
  users: [
    {
      id: ANALYST_ID,
      email: 'analyst@example.com',
      password: 'demo12345',
      displayName: 'Анна Ковалёва',
      createdAt: daysAgo(42),
      lastLoginAt: daysAgo(0, 2),
    },
    {
      id: GUEST_ID,
      email: 'guest@example.com',
      password: 'demo12345',
      displayName: 'Иван Петров',
      createdAt: daysAgo(12),
      lastLoginAt: null,
    },
  ],
  projects: [
    {
      id: ORDERS_PROJECT_ID,
      ownerId: ANALYST_ID,
      name: 'Модуль заявок',
      description: 'Создание, согласование и исполнение заявки на закупку',
      createdAt: daysAgo(21),
      updatedAt: daysAgo(1, 3),
    },
    {
      id: LIMITS_PROJECT_ID,
      ownerId: ANALYST_ID,
      name: 'Лимиты счёта',
      description: 'Проверка остатка и блокировка операций сверх лимита',
      createdAt: daysAgo(9),
      updatedAt: daysAgo(3),
    },
    {
      id: CONTRACTS_PROJECT_ID,
      ownerId: GUEST_ID,
      name: 'Согласование договоров',
      description: 'Маршрут согласования договора между подразделениями',
      createdAt: daysAgo(5),
      updatedAt: daysAgo(5),
    },
  ],
  requirements: [
    {
      id: '7a1c93b4-1d20-4a6f-9b3e-5c8d0e1f2a01',
      projectId: ORDERS_PROJECT_ID,
      version: 1,
      rawText: `Заявка создаётся в статусе «Черновик».
Менеджер может согласовать заявку или отклонить её.
После согласования заявка исполняется бухгалтерией.`,
      isCurrent: false,
      createdAt: daysAgo(20),
    },
    {
      id: '7a1c93b4-1d20-4a6f-9b3e-5c8d0e1f2a02',
      projectId: ORDERS_PROJECT_ID,
      version: 2,
      rawText: `Заявка создаётся в статусе «Черновик».
Менеджер может согласовать заявку или отклонить её.
Отклонённую заявку согласовать повторно нельзя.
После согласования заявка исполняется бухгалтерией.
Исполненную заявку отменить нельзя, но можно создать новую.`,
      isCurrent: true,
      createdAt: daysAgo(1, 3),
    },
    {
      id: '7a1c93b4-1d20-4a6f-9b3e-5c8d0e1f2a03',
      projectId: CONTRACTS_PROJECT_ID,
      version: 1,
      rawText: `Договор проходит согласование у юриста, затем у финансового директора.
Если финансовый директор отклонил договор, юрист может изменить условия и отправить его снова.`,
      isCurrent: true,
      createdAt: daysAgo(5),
    },
  ],
  models: buildSeedModels(),
  verifications: buildSeedVerifications(),
  sessions: [],
  fallbackToken: null,
})

const loadDatabase = (): MockDatabase => {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)

    if (raw !== null) {
      const parsed = JSON.parse(raw) as Partial<MockDatabase>

      if (
        parsed.schemaVersion === MOCK_SCHEMA_VERSION &&
        Array.isArray(parsed.models) &&
        Array.isArray(parsed.verifications)
      ) {
        return parsed as MockDatabase
      }
    }
  } catch {
    return seedDatabase()
  }

  return seedDatabase()
}

const database = loadDatabase()

const persist = (): void => {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(database))
  } catch {
    return
  }
}

export const getFallbackToken = (): string | null => database.fallbackToken

export const setFallbackToken = (token: string | null): void => {
  database.fallbackToken = token
  persist()
}

export const findUserByEmail = (email: string): MockUserRecord | null =>
  database.users.find((user) => user.email.toLowerCase() === email.toLowerCase()) ?? null

export const findUserById = (userId: string): MockUserRecord | null =>
  database.users.find((user) => user.id === userId) ?? null

export const createUser = (
  email: string,
  password: string,
  displayName: string | null,
): MockUserRecord => {
  const user: MockUserRecord = {
    id: crypto.randomUUID(),
    email,
    password,
    displayName,
    createdAt: new Date().toISOString(),
    lastLoginAt: new Date().toISOString(),
  }

  database.users.push(user)
  persist()

  return user
}

export const touchLastLogin = (userId: string): void => {
  const user = findUserById(userId)

  if (user !== null) {
    user.lastLoginAt = new Date().toISOString()
    persist()
  }
}

export const startSession = (userId: string): MockSessionRecord => {
  const session: MockSessionRecord = {
    token: crypto.randomUUID(),
    userId,
    expiresAt: Date.now() + 60 * 60 * 1000,
  }

  database.sessions.push(session)
  persist()

  return session
}

export const resolveSessionUser = (token: string | null): MockUserRecord | null => {
  if (token === null) {
    return null
  }

  const index = database.sessions.findIndex((session) => session.token === token)

  if (index === -1) {
    return null
  }

  const session = database.sessions[index]

  if (session === undefined || session.expiresAt < Date.now()) {
    database.sessions.splice(index, 1)
    persist()
    return null
  }

  return findUserById(session.userId)
}

export const destroySession = (token: string | null): void => {
  if (token === null) {
    return
  }

  database.sessions = database.sessions.filter((session) => session.token !== token)
  persist()
}

export const profileSummaryFor = (userId: string): ProfileSummaryRecord | null => {
  const user = findUserById(userId)

  if (user === null) {
    return null
  }

  const projectIds = new Set(
    database.projects.filter((project) => project.ownerId === userId).map((p) => p.id),
  )
  const requirements = database.requirements.filter((item) => projectIds.has(item.projectId))
  const verifications = database.verifications
    .filter((item) => projectIds.has(item.projectId))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))

  return {
    user,
    projectsCount: projectIds.size,
    requirementVersionsCount: requirements.length,
    verificationCount: verifications.length,
    violationCount: verifications.filter((item) => item.status === 'PROPERTY_VIOLATED').length,
    lastVerificationAt: verifications.at(0)?.createdAt ?? null,
  }
}

export const listProjectsByOwner = (ownerId: string): MockProjectRecord[] =>
  database.projects
    .filter((project) => project.ownerId === ownerId)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))

export const findOwnedProject = (projectId: string, ownerId: string): MockProjectRecord | null =>
  database.projects.find((project) => project.id === projectId && project.ownerId === ownerId) ??
  null

export const insertProject = (
  ownerId: string,
  name: string,
  description: string | null,
): MockProjectRecord => {
  const timestamp = new Date().toISOString()
  const project: MockProjectRecord = {
    id: crypto.randomUUID(),
    ownerId,
    name,
    description,
    createdAt: timestamp,
    updatedAt: timestamp,
  }

  database.projects.push(project)
  persist()

  return project
}

export const patchProject = (
  project: MockProjectRecord,
  name: string,
  description: string | null,
): MockProjectRecord => {
  project.name = name
  project.description = description
  project.updatedAt = new Date().toISOString()
  persist()

  return project
}

export const listRequirements = (projectId: string): MockRequirementRecord[] =>
  database.requirements
    .filter((requirement) => requirement.projectId === projectId)
    .sort((left, right) => right.version - left.version)

export const findOwnedRequirement = (
  requirementId: string,
  ownerId: string,
): MockRequirementRecord | null =>
  database.requirements.find((requirement) => {
    if (requirement.id !== requirementId) {
      return false
    }

    return findOwnedProject(requirement.projectId, ownerId) !== null
  }) ?? null

export const insertRequirement = (projectId: string, rawText: string): MockRequirementRecord => {
  const existing = listRequirements(projectId)
  const nextVersion = existing.length === 0 ? 1 : (existing[0]?.version ?? 0) + 1

  for (const requirement of existing) {
    requirement.isCurrent = false
  }

  const requirement: MockRequirementRecord = {
    id: crypto.randomUUID(),
    projectId,
    version: nextVersion,
    rawText,
    isCurrent: true,
    createdAt: new Date().toISOString(),
  }

  database.requirements.push(requirement)
  persist()

  return requirement
}

export const listModelVersions = (projectId: string): MockModelRecord[] =>
  database.models
    .filter((model) => model.projectId === projectId)
    .sort((left, right) => right.version - left.version)

export const currentModelVersion = (projectId: string): MockModelRecord | null =>
  listModelVersions(projectId).at(0) ?? null

const completeDueRuns = (): void => {
  const now = Date.now()
  let changed = false

  for (const verification of database.verifications) {
    if (verification.status !== 'PENDING' || verification.startedAt === null) {
      continue
    }

    const elapsed = now - verification.startedAt

    if (elapsed < MOCK_RUN_DURATION_MS) {
      continue
    }

    const model = database.models.find((item) => item.id === verification.modelVersionId)

    if (model === undefined) {
      continue
    }

    Object.assign(verification, outcomeFor(model.outcome, model), {
      status: model.outcome,
      durationMs: elapsed,
    })

    changed = true
  }

  if (changed) {
    persist()
  }
}

export const listVerifications = (projectId: string): MockVerificationRecord[] => {
  completeDueRuns()

  return database.verifications
    .filter((verification) => verification.projectId === projectId)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
}

export const insertVerification = (
  projectId: string,
  modelVersionId: string,
): MockVerificationRecord => {
  const verification: MockVerificationRecord = {
    id: crypto.randomUUID(),
    projectId,
    modelVersionId,
    propertyId: null,
    status: 'PENDING' satisfies VerificationStatus,
    engine: 'TLC',
    engineVersion: null,
    statistics: null,
    counterexample: null,
    relatedRequirements: [],
    durationMs: null,
    errorDetail: null,
    businessSummary: '',
    hypothesis: null,
    question: null,
    createdAt: new Date().toISOString(),
    startedAt: Date.now(),
  }

  database.verifications.push(verification)
  persist()

  return verification
}
