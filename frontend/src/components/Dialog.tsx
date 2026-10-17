import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { ANIMATION, MOTION_MEDIA, canAnimate } from '../lib/motion'
import { Button } from './Button'
import { Icon } from './Icon'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export interface DialogProps {
  open: boolean
  title: string
  description?: string | null
  onClose: () => void
  footer?: ReactNode
  children: ReactNode
}

export function Dialog({
  open,
  title,
  description = null,
  onClose,
  footer,
  children,
}: DialogProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) {
      return
    }

    const container = containerRef.current
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null

    container?.focus({ preventScroll: true })

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()

        return
      }

      if (event.key !== 'Tab' || container === null) {
        return
      }

      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => element.tabIndex >= 0 && element.offsetParent !== null)

      const first = focusable[0]
      const last = focusable.at(-1)

      if (first === undefined || last === undefined) {
        event.preventDefault()
        container.focus()

        return
      }

      const active = document.activeElement

      if (event.shiftKey && (active === first || active === container)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
      trigger?.focus({ preventScroll: true })
    }
  }, [open, onClose])

  useGSAP(
    () => {
      const container = containerRef.current

      if (!open || container === null || !canAnimate()) {
        return
      }

      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.fromTo(
          container,
          { opacity: 0, y: 18, scale: 0.97 },
          { opacity: 1, y: 0, scale: 1, duration: ANIMATION.base, ease: 'power3.out' },
        )
      })
    },
    { scope: containerRef, dependencies: [open] },
  )

  if (!open) {
    return null
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center overflow-y-auto p-4 sm:items-center">
      <button
        type="button"
        aria-label="Закрыть окно"
        onClick={onClose}
        className="fixed inset-0 cursor-default bg-canvas-deep/85 backdrop-blur-sm"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="panel relative w-full max-w-lg p-6 focus:outline-none"
      >
        <header className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-title font-semibold">{title}</h2>
            {description !== null ? <p className="text-sm text-muted">{description}</p> : null}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Закрыть">
            <Icon name="close" />
          </Button>
        </header>

        <div className="mt-6">{children}</div>

        {footer !== undefined ? <div className="mt-6 flex justify-end gap-2">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  )
}
