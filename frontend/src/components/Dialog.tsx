import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { ANIMATION, MOTION_MEDIA } from '../lib/motion'
import { Button } from './Button'

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

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  useGSAP(
    () => {
      const container = containerRef.current

      if (!open || container === null) {
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
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="panel relative w-full max-w-lg p-6"
      >
        <header className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-title font-semibold tracking-tight">{title}</h2>
            {description !== null ? <p className="text-sm text-muted">{description}</p> : null}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Закрыть">
            ✕
          </Button>
        </header>

        <div className="mt-6">{children}</div>

        {footer !== undefined ? <div className="mt-6 flex justify-end gap-2">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  )
}
