import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export type IconName =
  | 'alert'
  | 'arrow-left'
  | 'check'
  | 'chevron'
  | 'clock'
  | 'close'
  | 'inbox'
  | 'moon'
  | 'plus'
  | 'search'
  | 'sun'

export interface IconProps {
  name: IconName
  className?: string
}

const ICON_CONTENT: Record<IconName, ReactNode> = {
  alert: (
    <>
      <circle cx="12" cy="12" r="9" stroke="currentColor" />
      <path d="M12 7.5v5.5" stroke="currentColor" strokeLinecap="round" />
      <circle cx="12" cy="16.3" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  'arrow-left': (
    <>
      <path d="M19 12H5" stroke="currentColor" strokeLinecap="round" />
      <path d="M11 6 5 12l6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  check: (
    <path
      d="m5 12.5 4.5 4.5L19 7"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  chevron: (
    <path d="m9.5 6 6 6-6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" stroke="currentColor" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeLinecap="round" />
    </>
  ),
  close: <path d="m6.5 6.5 11 11m0-11-11 11" stroke="currentColor" strokeLinecap="round" />,
  inbox: (
    <>
      <path
        d="M4 13.5 6 5.5h12l2 8"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4 13.5h4.5l1 2.5h5l1-2.5H20v4a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </>
  ),
  moon: (
    <path
      d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
      stroke="currentColor"
      strokeLinejoin="round"
    />
  ),
  plus: <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" stroke="currentColor" />
      <path
        d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"
        stroke="currentColor"
        strokeLinecap="round"
      />
    </>
  ),
}

export function Icon({ name, className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      fill="none"
      strokeWidth="1.6"
      className={cn('size-4', className)}
    >
      {ICON_CONTENT[name]}
    </svg>
  )
}
