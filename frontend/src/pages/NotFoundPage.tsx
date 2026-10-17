import { Link } from 'react-router-dom'

import { useDocumentTitle } from '../lib/useDocumentTitle'
import { Icon } from '../components/Icon'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'

export function NotFoundPage() {
  useDocumentTitle('Страница не найдена')
  return (
    <div className="flex min-h-dvh items-center justify-center bg-fade-bottom px-5">
      <EmptyState
        icon={<Icon name="search" className="size-5" />}
        title="Такой страницы нет"
        description="Ссылка устарела или адрес введён с ошибкой"
        className="max-w-lg"
        action={
          <Link to="/projects">
            <Button variant="secondary">На главную</Button>
          </Link>
        }
      />
    </div>
  )
}
