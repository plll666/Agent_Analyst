import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from './Icon'
import { Button } from './Button'
import { EmptyState } from './EmptyState'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  failed: boolean
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Agent Analyst] Ошибка рендера', error, info.componentStack)
  }

  private readonly handleRetry = (): void => {
    this.setState({ failed: false })
  }

  override render(): ReactNode {
    if (!this.state.failed) {
      return this.props.children
    }

    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4 py-16 sm:px-6">
        <EmptyState
          icon={<Icon name="alert" className="size-5" />}
          title="Что-то сломалось на странице"
          description="Интерфейс не смог отобразить данные. Попробуйте повторить — если не поможет, обновите страницу. Возможно, API вернул ответ, которого фронт пока не понимает."
          className="w-full"
          action={
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button variant="secondary" onClick={this.handleRetry}>
                Попробовать снова
              </Button>
              <Link to="/projects">
                <Button variant="ghost">На главную</Button>
              </Link>
            </div>
          }
        />
      </div>
    )
  }
}
