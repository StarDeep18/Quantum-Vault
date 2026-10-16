import { lazy, Suspense } from 'react'
import type { Theme } from '../types'
import { VaultSilhouette } from './VaultSilhouette'

const DeferredScene = lazy(() => import('./VaultScene').then((module) => ({ default: module.VaultScene })))

interface SceneProps {
  open?: boolean
  theme?: Theme
  className?: string
  interactive?: boolean
  scrollMotion?: boolean
}

export function VaultScene(props: SceneProps) {
  return (
    <Suspense fallback={<VaultSilhouette className={props.className || ''} />}>
      <DeferredScene {...props} />
    </Suspense>
  )
}
