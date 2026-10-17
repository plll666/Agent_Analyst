import { apiRequest, HTTP_METHODS } from '../../lib/apiClient'
import { decodeUser, decodeVoid } from '../../lib/decode'
import type { AuthCredentials, RegistrationPayload, User } from '../../types/api'

const AUTH_PATH = '/auth'

export const register = (payload: RegistrationPayload): Promise<User> =>
  apiRequest(`${AUTH_PATH}/register`, decodeUser, {
    method: HTTP_METHODS.post,
    body: payload,
  })

export const login = (payload: AuthCredentials): Promise<User> =>
  apiRequest(`${AUTH_PATH}/login`, decodeUser, {
    method: HTTP_METHODS.post,
    body: payload,
  })

export const logout = (): Promise<undefined> =>
  apiRequest(`${AUTH_PATH}/logout`, decodeVoid, { method: HTTP_METHODS.post })

export const fetchCurrentUser = (): Promise<User> => apiRequest(`${AUTH_PATH}/me`, decodeUser)
