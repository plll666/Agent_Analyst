import { Link, Outlet } from 'react-router-dom'

import { useLogout } from '../features/auth/useLogout'
import { useSession } from '../features/auth/useSession'
import { ThemeToggle } from './ThemeToggle'
import { Button } from './Button'
import { Logo } from './Logo'

export function AppShell() {
  const session = useSession()
  const logout = useLogout()

  const user = session.data ?? null

  return (
    <div className="relative isolate flex min-h-dvh flex-col bg-fade-bottom">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-halo" />
      <div className="pointer-events-none fixed inset-0 -z-10 bg-grid opacity-70" />

      <header className="sticky top-0 z-40 shrink-0 border-b border-line bg-canvas/85 backdrop-blur-xl">
        <div className="@container mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:h-16 sm:px-6 lg:max-w-7xl xl:max-w-[92rem] 2xl:max-w-[104rem] 2xl:px-10">
          <Link to="/projects" className="flex items-center gap-2.5">
            <Logo className="size-8" />
            <span className="hidden text-sm font-semibold tracking-tight @md:block">
              Agent Analyst
            </span>
          </Link>

          <div className="flex items-center gap-2">
            <Link
              to="/profile"
              className="flex items-center gap-2 rounded-field px-2 py-1.5 text-sm text-muted transition-colors hover:bg-raised hover:text-fg"
              title="Профиль"
            >
              <span className="hidden max-w-52 truncate text-xs @md:block">{user?.email}</span>
              <span className="flex size-7 items-center justify-center rounded-full border border-bone/25 bg-bone-soft/50 text-xs font-semibold text-bone">
                {(user?.display_name ?? user?.email ?? '?').slice(0, 1).toUpperCase()}
              </span>
            </Link>

            <ThemeToggle variant="icon" />

            <Button
              variant="secondary"
              loading={logout.isPending}
              className="h-9 lg:h-10"
              onClick={() => logout.mutate()}
            >
              Выйти
            </Button>
          </div>
        </div>
      </header>

      <main className="@container mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-6 sm:px-6 lg:max-w-7xl lg:py-10 xl:max-w-[92rem] xl:px-8 2xl:max-w-[104rem] 2xl:px-10">
        <Outlet />
      </main>
    </div>
  )
}
