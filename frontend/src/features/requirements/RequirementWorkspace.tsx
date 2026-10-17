import { useRef, useState } from 'react'
import { useGSAP } from '@gsap/react'
import gsap from 'gsap'

import { ANIMATION, MOTION_MEDIA } from '../../lib/motion'
import type { Requirement } from '../../types/api'
import { RequirementEditor } from './RequirementEditor'
import { VersionHistory } from './VersionHistory'

export interface RequirementWorkspaceProps {
  projectId: string
  versions: Requirement[]
}

export function RequirementWorkspace({ projectId, versions }: RequirementWorkspaceProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const currentVersion = versions.find((version) => version.is_current) ?? null
  const selectedVersion =
    versions.find((version) => version.id === selectedId) ??
    currentVersion ??
    versions.at(0) ??
    null

  const hasHistory = versions.length > 0

  useGSAP(
    () => {
      const root = rootRef.current

      if (root === null) {
        return
      }

      const media = gsap.matchMedia()

      media.add(MOTION_MEDIA, () => {
        const targets = Array.from(root.querySelectorAll('[data-panel]'))

        if (targets.length === 0) {
          return
        }

        gsap.from(targets, {
          y: 18,
          opacity: 0,
          duration: ANIMATION.base,
          ease: 'power3.out',
          stagger: ANIMATION.stagger,
        })
      })
    },
    { scope: rootRef, dependencies: [versions.length] },
  )

  const handleSelect = (version: Requirement) => setSelectedId(version.id)
  const handleGoToCurrent = () => setSelectedId(null)

  const handleSaved = (requirement: Requirement) => setSelectedId(requirement.id)

  return (
    <div
      ref={rootRef}
      className={
        hasHistory
          ? 'grid items-start gap-5 @4xl:grid-cols-[minmax(0,17rem)_minmax(0,1fr)] @6xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]'
          : 'flex flex-col gap-5'
      }
    >
      {hasHistory ? (
        <div data-panel="history">
          <VersionHistory
            versions={versions}
            selectedId={selectedVersion?.id ?? null}
            onSelect={handleSelect}
          />
        </div>
      ) : null}

      <div data-panel="editor" key={selectedVersion?.id ?? 'draft'}>
        <RequirementEditor
          projectId={projectId}
          requirement={selectedVersion}
          onGoToCurrent={handleGoToCurrent}
          onSaved={handleSaved}
        />
      </div>
    </div>
  )
}
