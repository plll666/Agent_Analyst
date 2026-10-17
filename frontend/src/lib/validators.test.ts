import { describe, expect, it } from 'vitest'

import {
  MAX_PROJECT_NAME_LENGTH,
  MIN_PASSWORD_LENGTH,
  validateEmail,
  validatePassword,
  validateProjectName,
  validateRequirementText,
} from './validators'

describe('validateEmail', () => {
  it('принимает обычный адрес', () => {
    expect(validateEmail('analyst@example.com')).toBeNull()
  })

  it('не считает адресом строку без домена', () => {
    expect(validateEmail('analyst@example')).not.toBeNull()
  })

  it('не считает адресом строку с пробелом', () => {
    expect(validateEmail('anna analyst@example.com')).not.toBeNull()
  })

  it('просит адрес, если поле пустое', () => {
    expect(validateEmail('   ')).toBe('Укажите email')
  })
})

describe('validatePassword', () => {
  it('принимает пароль достаточной длины', () => {
    expect(validatePassword('demo12345')).toBeNull()
  })

  it('отклоняет короткий пароль и называет минимальную длину', () => {
    expect(validatePassword('demo12')).toBe(`Пароль не короче ${MIN_PASSWORD_LENGTH} символов`)
  })

  it('просит пароль, если поле пустое', () => {
    expect(validatePassword('')).toBe('Укажите пароль')
  })
})

describe('validateProjectName', () => {
  it('принимает название проекта', () => {
    expect(validateProjectName('Модуль заявок')).toBeNull()
  })

  it('отклоняет пустое название', () => {
    expect(validateProjectName('  ')).toBe('Укажите название проекта')
  })

  it('ограничивает длину названия', () => {
    expect(validateProjectName('а'.repeat(MAX_PROJECT_NAME_LENGTH + 1))).toBe(
      `Не длиннее ${MAX_PROJECT_NAME_LENGTH} символов`,
    )
  })

  it('принимает название ровно на пределе', () => {
    expect(validateProjectName('а'.repeat(MAX_PROJECT_NAME_LENGTH))).toBeNull()
  })
})

describe('validateRequirementText', () => {
  it('принимает непустой текст', () => {
    expect(validateRequirementText('Заявка после согласования может быть исполнена.')).toBeNull()
  })

  it('отклоняет текст из одних пробелов', () => {
    expect(validateRequirementText('   \n  ')).toBe('Требование пока пустое')
  })

  it('отклоняет пустую строку', () => {
    expect(validateRequirementText('')).toBe('Требование пока пустое')
  })
})
