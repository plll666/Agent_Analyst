import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useDocumentTitle } from '../lib/useDocumentTitle'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { toUserMessage } from '../lib/errors'
import { validateEmail, validatePassword } from '../lib/validators'
import { AuthLayout } from '../features/auth/AuthLayout'
import { useRegister } from '../features/auth/useRegister'

interface FieldErrors {
  displayName: string | null
  email: string | null
  password: string | null
  passwordRepeat: string | null
}

const EMPTY_ERRORS: FieldErrors = {
  displayName: null,
  email: null,
  password: null,
  passwordRepeat: null,
}

export function RegisterPage() {
  useDocumentTitle('Регистрация')
  const navigate = useNavigate()
  const registerMutation = useRegister()

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordRepeat, setPasswordRepeat] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>(EMPTY_ERRORS)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const trimmedName = displayName.trim()
    const errors: FieldErrors = {
      displayName: null,
      email: validateEmail(email),
      password: validatePassword(password),
      passwordRepeat: password === passwordRepeat ? null : 'Пароли не совпадают',
    }

    setFieldErrors(errors)

    if (Object.values(errors).some((error) => error !== null)) {
      return
    }

    try {
      await registerMutation.mutateAsync({
        email: email.trim(),
        password,
        display_name: trimmedName === '' ? null : trimmedName,
      })
      void navigate('/projects', { replace: true })
    } catch {
      return
    }
  }

  return (
    <AuthLayout
      headline="Начните с текста требования"
      subline="Проект — это один анализируемый модуль. Внутри него хранится требование и его версии, чтобы к каждому прогону модели можно было вернуться."
      highlights={[
        'Регистрация занимает меньше минуты',
        'Требования и версии приватны по умолчанию',
        'Ничего не нужно настраивать перед стартом',
      ]}
      footer={
        <span>
          Уже есть аккаунт?{' '}
          <Link to="/login" className="font-medium text-bone transition-colors hover:text-fg">
            Войти
          </Link>
        </span>
      }
    >
      <h2 className="text-xl font-semibold tracking-tight">Регистрация</h2>
      <p className="mt-1.5 text-sm text-muted">Создайте аккаунт и первый проект</p>

      <form className="mt-6 space-y-4" onSubmit={(event) => void handleSubmit(event)} noValidate>
        <Field id="display-name" label="Имя" hint="Необязательно">
          <Input
            id="display-name"
            name="displayName"
            type="text"
            autoComplete="name"
            placeholder="Как вас представить"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </Field>

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

        <Field id="password" label="Пароль" error={fieldErrors.password} hint="Минимум 8 символов">
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            value={password}
            invalid={fieldErrors.password !== null}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        <Field id="password-repeat" label="Повторите пароль" error={fieldErrors.passwordRepeat}>
          <Input
            id="password-repeat"
            name="passwordRepeat"
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            value={passwordRepeat}
            invalid={fieldErrors.passwordRepeat !== null}
            onChange={(event) => setPasswordRepeat(event.target.value)}
          />
        </Field>

        {registerMutation.error !== null ? (
          <p
            role="alert"
            className="rounded-field border border-danger/30 bg-surface-danger px-3.5 py-2.5 text-sm text-danger"
          >
            {toUserMessage(registerMutation.error)}
          </p>
        ) : null}

        <Button type="submit" size="lg" className="w-full" loading={registerMutation.isPending}>
          Создать аккаунт
        </Button>
      </form>
    </AuthLayout>
  )
}
