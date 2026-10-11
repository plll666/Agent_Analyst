import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import './index.css'

const container = document.getElementById('root')

if (container === null) {
  throw new Error('В index.html нет элемента с id="root"')
}

createRoot(container).render(
  <StrictMode>
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Agent Analyst</h1>
      <p className="mt-2 text-gray-600">
        Трек agent analyst: текст требований → формальная модель → проверка → объяснение.
      </p>
    </main>
  </StrictMode>,
)
