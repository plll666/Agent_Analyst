import { delay, http, HttpResponse } from 'msw'
import type { PathParams } from 'msw'

import type { MockProjectRecord, MockRequirementRecord, MockUserRecord } from './store'
import type { MockModelRecord, MockVerificationRecord } from './store'
import {
  createUser,
  currentModelVersion,
  destroySession,
  findOwnedProject,
  findOwnedRequirement,
  findUserByEmail,
  getFallbackToken,
  insertProject,
  insertRequirement,
  insertVerification,
  listModelVersions,
  listProjectsByOwner,
  listRequirements,
  listVerifications,
  patchProject,
  profileSummaryFor,
  resolveSessionUser,
  setFallbackToken,
  startSession,
  touchLastLogin,
} from './store'

const SESSION_COOKIE_NAME = 'session'
const MIN_PASSWORD_LENGTH = 8
const MAX_PROJECT_NAME_LENGTH = 200

const latency = (): number => 120 + Math.round(Math.random() * 180)

const errorResponse = (status: number, code: string, message: string) =>
  HttpResponse.json({ detail: { code, message } }, { status })

const unauthorized = () =>
  errorResponse(401, 'UNAUTHENTICATED', 'Сессия закончилась. Войдите заново.')

const notFound = () =>
  errorResponse(404, 'NOT_FOUND', 'Проект не найден или принадлежит другому пользователю')

const validationError = (message: string) => errorResponse(422, 'VALIDATION_ERROR', message)

const readParam = (params: PathParams, name: string): string => {
  const value = params[name]

  if (typeof value === 'string') {
    return value
  }

  return Array.isArray(value) ? (value.at(0) ?? '') : ''
}

const readString = (source: Record<string, unknown>, key: string): string | null => {
  const value = source[key]

  return typeof value === 'string' ? value : null
}

const asRecord = (payload: unknown): Record<string, unknown> => {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    return {}
  }

  return payload as Record<string, unknown>
}

const readCookie = (request: Request, name: string): string | null => {
  const header = request.headers.get('cookie')

  if (header === null) {
    return null
  }

  const pair = header
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`))

  return pair === undefined ? null : decodeURIComponent(pair.slice(name.length + 1))
}

const resolveUser = (request: Request): MockUserRecord | null =>
  resolveSessionUser(readCookie(request, SESSION_COOKIE_NAME) ?? getFallbackToken())

const buildCookie = (token: string): string =>
  `${SESSION_COOKIE_NAME}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`

const clearedCookie = (): string =>
  `${SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`

const openSession = (userId: string): string => {
  const session = startSession(userId)
  setFallbackToken(session.token)

  return buildCookie(session.token)
}

const trimmedOrNull = (value: string | null): string | null => {
  if (value === null || value.trim() === '') {
    return null
  }

  return value.trim()
}

const toUserResponse = (user: MockUserRecord) => ({
  id: user.id,
  email: user.email,
  display_name: user.displayName,
  created_at: user.createdAt,
  last_login_at: user.lastLoginAt,
})

const toProjectResponse = (project: MockProjectRecord) => ({
  id: project.id,
  name: project.name,
  description: project.description,
  created_at: project.createdAt,
  updated_at: project.updatedAt,
})

const toRequirementResponse = (requirement: MockRequirementRecord) => ({
  id: requirement.id,
  project_id: requirement.projectId,
  version: requirement.version,
  raw_text: requirement.rawText,
  is_current: requirement.isCurrent,
  created_at: requirement.createdAt,
})

const toModelVersionResponse = (model: MockModelRecord) => ({
  id: model.id,
  project_id: model.projectId,
  version: model.version,
  source: model.source,
  schema_hash: model.schemaHash,
  validation_status: model.validationStatus,
  validation_errors: model.validationErrors,
  document: model.document,
  created_at: model.createdAt,
})

const toVerificationResponse = (verification: MockVerificationRecord) => ({
  id: verification.id,
  project_id: verification.projectId,
  model_version_id: verification.modelVersionId,
  property_id: verification.propertyId,
  status: verification.status,
  engine: verification.engine,
  engine_version: verification.engineVersion,
  statistics: verification.statistics,
  counterexample: verification.counterexample,
  related_requirements: verification.relatedRequirements,
  duration_ms: verification.durationMs,
  error_detail: verification.errorDetail,
  business_summary: verification.businessSummary,
  hypothesis: verification.hypothesis,
  question: verification.question,
  created_at: verification.createdAt,
})

export const mockHandlers = [
  http.post('/api/auth/register', async ({ request }) => {
    await delay(latency())

    const source = asRecord(await request.json().catch(() => null))
    const email = (readString(source, 'email') ?? '').trim()
    const password = readString(source, 'password') ?? ''

    if (email === '' || password.length < MIN_PASSWORD_LENGTH) {
      return validationError(`Нужен email и пароль не короче ${MIN_PASSWORD_LENGTH} символов`)
    }

    if (findUserByEmail(email) !== null) {
      return errorResponse(409, 'EMAIL_TAKEN', 'Этот email уже зарегистрирован')
    }

    const user = createUser(email, password, trimmedOrNull(readString(source, 'display_name')))

    return HttpResponse.json(toUserResponse(user), {
      status: 201,
      headers: { 'Set-Cookie': openSession(user.id) },
    })
  }),

  http.post('/api/auth/login', async ({ request }) => {
    await delay(latency())

    const source = asRecord(await request.json().catch(() => null))
    const email = (readString(source, 'email') ?? '').trim()
    const password = readString(source, 'password') ?? ''
    const user = findUserByEmail(email)

    if (user === null || user.password !== password) {
      return errorResponse(401, 'INVALID_CREDENTIALS', 'Неверный email или пароль')
    }

    touchLastLogin(user.id)

    return HttpResponse.json(toUserResponse(user), {
      status: 200,
      headers: { 'Set-Cookie': openSession(user.id) },
    })
  }),

  http.post('/api/auth/logout', async ({ request }) => {
    await delay(latency())

    destroySession(readCookie(request, SESSION_COOKIE_NAME) ?? getFallbackToken())
    setFallbackToken(null)

    return new HttpResponse(null, { status: 204, headers: { 'Set-Cookie': clearedCookie() } })
  }),

  http.get('/api/auth/me', async ({ request }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    return HttpResponse.json(toUserResponse(user))
  }),

  http.get('/api/users/me/summary', async ({ request }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const summary = profileSummaryFor(user.id)

    if (summary === null) {
      return unauthorized()
    }

    return HttpResponse.json({
      user: toUserResponse(summary.user),
      projects_count: summary.projectsCount,
      requirement_versions_count: summary.requirementVersionsCount,
      verification_count: summary.verificationCount,
      violation_count: summary.violationCount,
      last_verification_at: summary.lastVerificationAt,
    })
  }),

  http.get('/api/projects', async ({ request }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    return HttpResponse.json({ items: listProjectsByOwner(user.id).map(toProjectResponse) })
  }),

  http.post('/api/projects', async ({ request }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const source = asRecord(await request.json().catch(() => null))
    const name = (readString(source, 'name') ?? '').trim()
    const description = trimmedOrNull(readString(source, 'description'))

    if (name === '') {
      return validationError('Укажите название проекта')
    }

    if (name.length > MAX_PROJECT_NAME_LENGTH) {
      return validationError(`Название не длиннее ${MAX_PROJECT_NAME_LENGTH} символов`)
    }

    return HttpResponse.json(toProjectResponse(insertProject(user.id, name, description)), {
      status: 201,
    })
  }),

  http.get('/api/projects/:projectId', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const project = findOwnedProject(readParam(params, 'projectId'), user.id)

    if (project === null) {
      return notFound()
    }

    return HttpResponse.json(toProjectResponse(project))
  }),

  http.patch('/api/projects/:projectId', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const project = findOwnedProject(readParam(params, 'projectId'), user.id)

    if (project === null) {
      return notFound()
    }

    const source = asRecord(await request.json().catch(() => null))
    const name = (readString(source, 'name') ?? '').trim()

    if (name === '' || name.length > MAX_PROJECT_NAME_LENGTH) {
      return validationError('Название проекта не заполнено или слишком длинное')
    }

    return HttpResponse.json(
      toProjectResponse(
        patchProject(project, name, trimmedOrNull(readString(source, 'description'))),
      ),
    )
  }),

  http.get('/api/projects/:projectId/requirements', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const projectId = readParam(params, 'projectId')

    if (findOwnedProject(projectId, user.id) === null) {
      return notFound()
    }

    return HttpResponse.json({ items: listRequirements(projectId).map(toRequirementResponse) })
  }),

  http.post('/api/projects/:projectId/requirements', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const projectId = readParam(params, 'projectId')

    if (findOwnedProject(projectId, user.id) === null) {
      return notFound()
    }

    const source = asRecord(await request.json().catch(() => null))
    const rawText = (readString(source, 'raw_text') ?? '').trim()

    if (rawText === '') {
      return validationError('Требование не может быть пустым')
    }

    return HttpResponse.json(toRequirementResponse(insertRequirement(projectId, rawText)), {
      status: 201,
    })
  }),

  http.get('/api/requirements/:requirementId', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const requirement = findOwnedRequirement(readParam(params, 'requirementId'), user.id)

    if (requirement === null) {
      return notFound()
    }

    return HttpResponse.json(toRequirementResponse(requirement))
  }),

  http.get('/api/projects/:projectId/models', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const projectId = readParam(params, 'projectId')

    if (findOwnedProject(projectId, user.id) === null) {
      return notFound()
    }

    return HttpResponse.json({ items: listModelVersions(projectId).map(toModelVersionResponse) })
  }),

  http.get('/api/projects/:projectId/verifications', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const projectId = readParam(params, 'projectId')

    if (findOwnedProject(projectId, user.id) === null) {
      return notFound()
    }

    return HttpResponse.json({ items: listVerifications(projectId).map(toVerificationResponse) })
  }),

  http.post('/api/projects/:projectId/verifications', async ({ request, params }) => {
    await delay(latency())

    const user = resolveUser(request)

    if (user === null) {
      return unauthorized()
    }

    const projectId = readParam(params, 'projectId')

    if (findOwnedProject(projectId, user.id) === null) {
      return notFound()
    }

    const model = currentModelVersion(projectId)

    if (model === null) {
      return validationError('Модель ещё не построена — проверять нечего')
    }

    return HttpResponse.json(toVerificationResponse(insertVerification(projectId, model.id)), {
      status: 201,
    })
  }),
]
