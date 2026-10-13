import { setupWorker } from 'msw/browser'

import { mockHandlers } from './handlers'

export const startMockServer = async (): Promise<void> => {
  const worker = setupWorker(...mockHandlers)

  await worker.start({ onUnhandledRequest: 'bypass', quiet: true })

  console.info('[Agent Analyst] Включён мок-API: запросы идут в память, backend не нужен')
}
