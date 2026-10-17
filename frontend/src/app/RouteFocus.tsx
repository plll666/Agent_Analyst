import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const FOCUSABLE_ATTRIBUTE = 'tabindex'

export function RouteFocus() {
  const { pathname } = useLocation()

  useEffect(() => {
    const main = document.querySelector<HTMLElement>('main')
    const heading = main?.querySelector<HTMLElement>('h1') ?? null
    const target = heading ?? main ?? null

    if (target === null) {
      return
    }

    if (!target.hasAttribute(FOCUSABLE_ATTRIBUTE)) {
      target.setAttribute(FOCUSABLE_ATTRIBUTE, '-1')
    }

    target.focus({ preventScroll: true })
  }, [pathname])

  return null
}
