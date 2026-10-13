import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { toUserMessage } from '../lib/errors'
import { validateEmail, validatePassword } from '../lib/validators'
import { AuthLayout } from '../features/auth/AuthLayout'
import { useLogin } from '../features/auth/useLogin'
import { isMockApiEnabled } from '../lib/env'

interface LoginFieldErrors {
  email: string | null
  password: string | null
}

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const loginMutation = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<LoginFieldErrors>({ email: null, password: null })

  const from = searchParams.get('from')
  const sessionExpired = searchParams.get('reason') === 'expired'

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)

    setFieldErrors({ email: emailError, password: passwordError })

    if (emailError !== null || passwordError !== null) {
      return
    }

    try {
      await loginMutation.mutateAsync({ email: email.trim(), password })
      void navigate(from ?? '/projects', { replace: true })
    } catch {
      return
    }
  }

  const fillDemoCredentials = () => {
    setEmail('analyst@example.com')
    setPassword('demo12345')
  }

  return (
    <AuthLayout
      headline="Требования, которые можно проверить"
      subline="Опишите поведение модуля текстом — агент построит формальную модель, движок переберёт состояния и вернёт контрпример, понятный бизнесу."
      highlights={[
        'История версий требования с сохранением каждой правки',
        'Модель поведения и результат проверки в одном месте',
        'Доступ к проектам только у их владельца',
      ]}
      footer={
        <span>
          Нет аккаунта?{' '}
          <Link to="/register" className="font-medium text-bone transition-colors hover:text-fg">
            Зарегистрироваться
          </Link>
        </span>
      }
    >
      <h2 className="text-xl font-semibold tracking-tight">Вход</h2>
      <p className="mt-1.5 text-sm text-muted">Продолжим с того места, где остановились</p>

      {sessionExpired ? (
        <div className="mt-5 rounded-field border border-danger/30 bg-surface-danger px-3.5 py-3 text-sm text-muted">
          Сессия закончилась. Войдите заново — проекты на месте.
        </div>
      ) : null}

      <form className="mt-6 space-y-4" onSubmit={(event) => void handleSubmit(event)} noValidate>
        <Field id="email" label="Email" error={fieldErrors.email}>
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            placeholder="analyst@example.com"
            value={email}
            invalid={fieldErrors.email !== null}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field id="password" label="Пароль" error={fieldErrors.password}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            invalid={fieldErrors.password !== null}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        {loginMutation.error !== null ? (
          <p
            role="alert"
            className="rounded-field border border-danger/30 bg-surface-danger px-3.5 py-2.5 text-sm text-danger"
          >
            {toUserMessage(loginMutation.error)}
          </p>
        ) : null}

        <Button type="submit" size="lg" className="w-full" loading={loginMutation.isPending}>
          Войти
        </Button>
      </form>

      {isMockApiEnabled ? (
        <div className="mt-6 rounded-field border border-line bg-raised/60 p-3.5">
          <p className="text-micro font-semibold tracking-[0.14em] text-subtle uppercase">
            Демо-доступы
          </p>
          <p className="mt-2 font-mono text-xs text-muted">analyst@example.com · demo12345</p>
          <p className="font-mono text-xs text-muted">guest@example.com · demo12345</p>
          <button
            type="button"
            onClick={fillDemoCredentials}
            className="-mx-2 mt-1 px-2 py-2.5 text-xs font-medium text-bone transition-colors hover:text-fg"
          >
            Подставить основной аккаунт
          </button>
        </div>
      ) : null}
    </AuthLayout>
  )
}
