import { describe, expect, it } from 'vitest'

import {
  formatDuration,
  pluralize,
  pluralizeProjects,
  pluralizeRequirements,
  pluralizeViolations,
} from './format'

describe('pluralize', () => {
  it('выбирает единственное число для 1', () => {
    expect(pluralize(1, 'проект', 'проекта', 'проектов')).toBe('1 проект')
  })

  it('выбирает форму для 2-4', () => {
    expect(pluralize(2, 'проект', 'проекта', 'проектов')).toBe('2 проекта')
    expect(pluralize(4, 'проект', 'проекта', 'проектов')).toBe('4 проекта')
  })

  it('выбирает множественное число для 5 и 0', () => {
    expect(pluralize(5, 'проект', 'проекта', 'проектов')).toBe('5 проектов')
    expect(pluralize(0, 'проект', 'проекта', 'проектов')).toBe('0 проектов')
  })

  it('не склоняет числа, оканчивающиеся на 11-14', () => {
    expect(pluralize(11, 'проект', 'проекта', 'проектов')).toBe('11 проектов')
    expect(pluralize(12, 'проект', 'проекта', 'проектов')).toBe('12 проектов')
    expect(pluralize(14, 'проект', 'проекта', 'проектов')).toBe('14 проектов')
  })

  it('учитывает последние две цифры при больших числах', () => {
    expect(pluralize(111, 'проект', 'проекта', 'проектов')).toBe('111 проектов')
    expect(pluralize(121, 'проект', 'проекта', 'проектов')).toBe('121 проект')
  })
})

describe('подписи счётчиков', () => {
  it('склоняет проекты', () => {
    expect(pluralizeProjects(1)).toBe('1 проект')
    expect(pluralizeProjects(3)).toBe('3 проекта')
    expect(pluralizeProjects(7)).toBe('7 проектов')
  })

  it('склоняет версии требований', () => {
    expect(pluralizeRequirements(1)).toBe('1 версия требования')
    expect(pluralizeRequirements(2)).toBe('2 версии требований')
    expect(pluralizeRequirements(5)).toBe('5 версий требований')
  })

  it('склоняет нарушения', () => {
    expect(pluralizeViolations(1)).toBe('1 нарушение')
    expect(pluralizeViolations(3)).toBe('3 нарушения')
    expect(pluralizeViolations(9)).toBe('9 нарушений')
  })
})

describe('formatDuration', () => {
  it('печатает миллисекунды как есть', () => {
    expect(formatDuration(812)).toBe('812 мс')
  })

  it('переводит секунды с запятой вместо точки', () => {
    expect(formatDuration(1500)).toBe('1,5 с')
    expect(formatDuration(640)).toBe('640 мс')
  })

  it('печатает ровно секунду', () => {
    expect(formatDuration(1000)).toBe('1,0 с')
  })
})
