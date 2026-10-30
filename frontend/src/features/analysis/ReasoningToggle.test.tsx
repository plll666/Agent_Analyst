import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReasoningToggle } from './ReasoningToggle'

describe('ReasoningToggle', () => {
  it('объясняет смысл словами, без терминов провайдера', () => {
    render(<ReasoningToggle checked={false} onChange={() => {}} />)

    expect(screen.getByRole('checkbox', { name: /рассуждать перед ответом/i })).not.toBeChecked()
    expect(screen.getByText(/продумывает требование/i)).toBeInTheDocument()
  })

  it('сообщает о включении', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ReasoningToggle checked={false} onChange={onChange} />)
    await user.click(screen.getByRole('checkbox'))

    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('не переключается, пока идёт запуск', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ReasoningToggle checked onChange={onChange} disabled />)
    await user.click(screen.getByRole('checkbox'))

    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByRole('checkbox')).toBeDisabled()
  })
})
