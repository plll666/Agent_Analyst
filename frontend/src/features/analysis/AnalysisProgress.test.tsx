import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VERIFICATION_STATUSES } from '../../types/api'
import type { AnalysisStage, Verification } from '../../types/api'
import { AnalysisProgress } from './AnalysisProgress'

const STARTED_AT = '2026-11-21T10:00:00.000Z'

const verification: Verification = {
  id: 'run-1',
  project_id: 'project-1',
  model_version_id: null,
  requirement_id: null,
  property_id: null,
  status: VERIFICATION_STATUSES.propertyViolated,
  engine: 'TLC',
  engine_version: '1.7.4',
  statistics: null,
  counterexample: null,
  related_requirements: [],
  duration_ms: null,
  error_detail: null,
  business_summary: '',
  hypothesis: null,
  question: null,
  root_cause: null,
  created_at: STARTED_AT,
  execution_status: 'RUNNING',
}

function stage(overrides: Partial<AnalysisStage> = {}): AnalysisStage {
  return {
    stage_id: 'stage-1',
    parent_stage_id: null,
    scope: 'agent',
    name: 'build',
    state: 'RUNNING',
    build_index: 0,
    attempt: 1,
    property_id: null,
    started_at: STARTED_AT,
    finished_at: null,
    duration_ms: null,
    reason_code: null,
    message: null,
    statistics: null,
    ...overrides,
  }
}

function renderProgress(stages: AnalysisStage[], run: Verification = verification) {
  return render(
    <AnalysisProgress
      verification={run}
      stages={stages}
      streamState="connected"
    />,
  )
}

afterEach(() => {
  vi.useRealTimers()
})

describe('AnalysisProgress — время выполнения этапа', () => {
  it('тик идёт, пока этап выполняется', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(STARTED_AT))

    renderProgress([stage()])

    expect(screen.getByText('0 мс')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(screen.getByText('2,0 с')).toBeInTheDocument()
  })

  it('показывает серверную длительность, когда этап завершён', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(STARTED_AT))

    renderProgress([stage({ state: 'SUCCEEDED', duration_ms: 4200 })])

    expect(screen.getByText('4,2 с')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(screen.getByText('4,2 с')).toBeInTheDocument()
  })

  it('обновляется чаще раза в секунду, чтобы цифры не прыгали', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(STARTED_AT))

    renderProgress([stage()])

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(screen.getByText('500 мс')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(screen.getByText('1,0 с')).toBeInTheDocument()
  })

  it('не создаёт таймер, когда выполняющихся этапов нет', () => {
    vi.useFakeTimers()
    const setInterval = vi.spyOn(window, 'setInterval')

    renderProgress([stage({ state: 'SUCCEEDED', duration_ms: 100 })])
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(setInterval).not.toHaveBeenCalled()
  })
})