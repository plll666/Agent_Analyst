import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { cn } from '../lib/cn'
import { ANIMATION, MOTION_MEDIA } from '../lib/motion'
import { ToastContext } from '../lib/toastContext'
import type { ToastApi, ToastItem, ToastTone } from '../lib/toastContext'

const TOAST_LIFETIME_MS = 5200

const TOAST_TONES: Record<ToastTone, string> = {
  info: 'border-line bg-overlay text-fg',
  success: 'border-line bg-overlay text-fg',
  danger: 'border-danger/40 bg-overlay text-fg',
}

const TOAST_ACCENTS: Record<ToastTone, string> = {
  info: 'bg-bone/60',
  success: 'bg-success',
  danger: 'bg-danger',
}

interface ToastCardProps {
  toast: ToastItem
  onDismiss: (id: number) => void
}

function ToastCard({ toast, onDismiss }: ToastCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        gsap.fromTo(
          cardRef.current,
          { opacity: 0, x: 28, scale: 0.96 },
          { opacity: 1, x: 0, scale: 1, duration: ANIMATION.base, ease: 'power3.out' },
        )
      })
    },
    { scope: cardRef },
  )

  useEffect(() => {
    const timeout = window.setTimeout(() => onDismiss(toast.id), TOAST_LIFETIME_MS)

    return () => window.clearTimeout(timeout)
  }, [onDismiss, toast.id])

  return (
    <div
      ref={cardRef}
      role="status"
      className={cn(
        'pointer-events-auto flex w-full items-start gap-3 overflow-hidden rounded-field border p-3.5 shadow-card',
        TOAST_TONES[toast.tone],
      )}
    >
      <span className={cn('mt-1 size-2 shrink-0 rounded-full', TOAST_ACCENTS[toast.tone])} />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description !== undefined ? (
          <p className="text-xs leading-relaxed text-muted">{toast.description}</p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Скрыть уведомление"
        className="-m-2 p-2 text-subtle transition-colors hover:text-fg"
      >
        ✕
      </button>
    </div>
  )
}

export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counterRef = useRef(0)

  const push = useCallback((toast: Parameters<ToastApi['push']>[0]) => {
    counterRef.current += 1
    const item: ToastItem = { ...toast, id: counterRef.current }

    setToasts((current) => [...current.slice(-2), item])
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const api = useMemo<ToastApi>(() => ({ push }), [push])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-60 flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:end-4 sm:bottom-4 sm:w-96 sm:items-end sm:p-0">
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
