import { AppProviders } from './AppProviders'
import { AppRoutes } from './AppRoutes'
import { ErrorBoundary } from '../components/ErrorBoundary'

export function App() {
  return (
    <AppProviders>
      <ErrorBoundary>
        <AppRoutes />
      </ErrorBoundary>
    </AppProviders>
  )
}
