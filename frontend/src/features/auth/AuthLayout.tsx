import { useRef } from 'react'
import type { PropsWithChildren, ReactNode } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { Logo } from '../../components/Logo'
import { ANIMATION, MOTION_MEDIA } from '../../lib/motion'

export interface AuthLayoutProps extends PropsWithChildren {
  headline: string
  subline: string
  highlights: string[]
  footer: ReactNode
}

export function AuthLayout({ headline, subline, highlights, footer, children }: AuthLayoutProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const words = headline.split(' ')

  useGSAP(
    () => {
      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        const timeline = gsap.timeline({ defaults: { ease: 'power3.out' } })

        timeline
          .from('[data-orbit="near"]', { opacity: 0, scale: 0.85, duration: ANIMATION.hero })
          .from(
            '[data-reveal="word"]',
            { yPercent: 115, opacity: 0, duration: ANIMATION.intro, stagger: ANIMATION.stagger },
            0.36,
          )
          .from('[data-reveal="form"]', { y: 26, opacity: 0, duration: ANIMATION.base }, 0.6)
          .from(
            '[data-reveal="highlight"]',
            { y: 14, opacity: 0, duration: ANIMATION.base, stagger: ANIMATION.stagger },
            1.1,
          )

        gsap.to('[data-orbit="near"]', {
          y: -26,
          x: 18,
          duration: 8,
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
        })

        gsap.to('[data-orbit="far"]', {
          y: 22,
          x: -20,
          duration: 10,
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
        })
      })
    },
    { scope: rootRef },
  )

  return (
    <div ref={rootRef} className="@container relative min-h-dvh overflow-hidden bg-fade-bottom">
      <div className="pointer-events-none absolute inset-0 bg-halo" />
      <div className="pointer-events-none absolute inset-0 bg-grid" />
      <div
        data-orbit="far"
        className="pointer-events-none absolute -top-32 -end-24 size-[32rem] rounded-full bg-bone/12 blur-[120px]"
      />
      <div
        data-orbit="near"
        className="pointer-events-none absolute -bottom-40 -start-28 size-[28rem] rounded-full bg-bone/8 blur-[140px]"
      />

      <div className="relative mx-auto grid min-h-dvh w-full max-w-6xl content-center items-center gap-10 px-5 py-12 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,25rem)] @4xl:gap-20 @4xl:px-8">
        <section className="hidden @4xl:block">
          <div className="flex items-center gap-3">
            <Logo />
            <span className="text-sm font-semibold tracking-tight">Agent Analyst</span>
          </div>

          <h1 className="mt-10 text-display font-semibold tracking-tight">
            {words.map((word, index) => (
              <span
                key={`${word}-${index}`}
                className="inline-block overflow-hidden align-bottom pe-[0.25em] pb-[0.14em] -mb-[0.14em]"
              >
                <span data-reveal="word" className="text-gradient inline-block">
                  {word}
                </span>
              </span>
            ))}
          </h1>

          <p className="mt-6 max-w-lg text-base leading-relaxed text-muted">{subline}</p>

          <ul className="mt-10 space-y-3">
            {highlights.map((highlight) => (
              <li
                key={highlight}
                data-reveal="highlight"
                className="flex items-center gap-3 text-sm text-muted"
              >
                <span className="flex size-5 items-center justify-center rounded-full border border-bone/30 bg-bone-soft/50 text-micro text-bone">
                  ✓
                </span>
                {highlight}
              </li>
            ))}
          </ul>
        </section>

        <section data-reveal="form" className="panel w-full p-7 @lg:p-8">
          <div className="@4xl:hidden">
            <div className="flex items-center gap-3">
              <Logo className="size-8" />
              <span className="text-sm font-semibold tracking-tight">Agent Analyst</span>
            </div>
          </div>

          <div className="@4xl:mt-0 mt-8">{children}</div>

          <div className="mt-7 border-t border-line pt-5 text-sm text-muted">{footer}</div>
        </section>
      </div>
    </div>
  )
}
