import { Logo } from './Logo'
import { Spinner } from './Spinner'

export function FullPageLoader() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-fade-bottom">
      <Logo className="animate-pulse" />
      <div className="flex items-center gap-2 text-sm text-subtle">
        <Spinner className="size-3.5" />
        <span>Загружаем данные</span>
      </div>
    </div>
  )
}
