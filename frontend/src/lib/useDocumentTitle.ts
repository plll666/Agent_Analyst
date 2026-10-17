import { useEffect } from 'react'

const APP_NAME = 'Agent Analyst'

export const useDocumentTitle = (title: string): void => {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`
  }, [title])
}
