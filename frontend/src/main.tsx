import '@fontsource-variable/golos-text'
import '@fontsource-variable/jetbrains-mono'
import './index.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app/App'
import { isMockApiEnabled } from './lib/env'

const container = document.getElementById('root')

if (container === null) {
  throw new Error('В index.html нет элемента с id="root"')
}

const bootstrap = async (): Promise<void> => {
  if (isMockApiEnabled) {
    const { startMockServer } = await import('./mocks/startMockServer')
    await startMockServer()
  }

  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void bootstrap()
