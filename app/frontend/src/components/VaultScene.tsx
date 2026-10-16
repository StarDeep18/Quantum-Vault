import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { Group } from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { Theme } from '../types'
import { VaultSilhouette } from './VaultSilhouette'

interface VaultSceneProps {
  open?: boolean
  theme?: Theme
  className?: string
  interactive?: boolean
  scrollMotion?: boolean
}

function VaultModel({ open, interactive, scrollMotion }: { open: boolean; interactive: boolean; scrollMotion: boolean }) {
  const root = useRef<Group>(null)
  const doorPivot = useRef<Group>(null)
  const wheel = useRef<Group>(null)
  const wheelTarget = useRef(0)
  const scrollProgress = useRef(0)
  const boltRefs = useRef<Array<Group | null>>([])
  const priorOpen = useRef(open)
  const [reducedMotion, setReducedMotion] = useState(false)

  const bodyGeometry = useMemo(() => new RoundedBoxGeometry(5.55, 5.62, 1.72, 7, 0.18), [])
  const faceGeometry = useMemo(() => new RoundedBoxGeometry(5.22, 5.28, 0.19, 7, 0.15), [])
  const innerFaceGeometry = useMemo(() => new RoundedBoxGeometry(4.91, 4.96, 0.11, 6, 0.12), [])
  const doorBackingGeometry = useMemo(() => new THREE.CylinderGeometry(2.16, 2.16, 0.37, 96, 1), [])
  const doorDiscGeometry = useMemo(() => new THREE.CylinderGeometry(1.91, 1.91, 0.13, 96, 1), [])
  const centerDiscGeometry = useMemo(() => new THREE.CylinderGeometry(0.76, 0.76, 0.17, 64, 1), [])
  const hubGeometry = useMemo(() => new THREE.CylinderGeometry(0.31, 0.31, 0.15, 48, 1), [])
  const boltGeometry = useMemo(() => new RoundedBoxGeometry(0.22, 0.48, 0.18, 4, 0.035), [])
  const rivetGeometry = useMemo(() => new THREE.SphereGeometry(0.058, 18, 14), [])
  const frameRing = useMemo(() => new THREE.TorusGeometry(2.03, 0.055, 14, 100), [])
  const innerRing = useMemo(() => new THREE.TorusGeometry(1.68, 0.027, 12, 100), [])
  const hubRing = useMemo(() => new THREE.TorusGeometry(0.67, 0.065, 16, 72), [])
  const hingeGeometry = useMemo(() => new THREE.CylinderGeometry(0.17, 0.17, 0.5, 32), [])
  const hingeCapGeometry = useMemo(() => new THREE.CylinderGeometry(0.19, 0.19, 0.09, 32), [])

  const materials = useMemo(() => ({
    shell: new THREE.MeshStandardMaterial({ color: '#3d4544', metalness: 0.78, roughness: 0.32 }),
    shellEdge: new THREE.MeshStandardMaterial({ color: '#626a67', metalness: 0.83, roughness: 0.29 }),
    face: new THREE.MeshStandardMaterial({ color: '#515956', metalness: 0.78, roughness: 0.31 }),
    faceDark: new THREE.MeshStandardMaterial({ color: '#333a39', metalness: 0.84, roughness: 0.3 }),
    panel: new THREE.MeshStandardMaterial({ color: '#484f4d', metalness: 0.82, roughness: 0.36 }),
    steel: new THREE.MeshStandardMaterial({ color: '#92958c', metalness: 0.9, roughness: 0.23 }),
    brushed: new THREE.MeshStandardMaterial({ color: '#777d76', metalness: 0.9, roughness: 0.32 }),
    brass: new THREE.MeshStandardMaterial({ color: '#a78a59', metalness: 0.76, roughness: 0.28 }),
    recess: new THREE.MeshStandardMaterial({ color: '#171d1d', metalness: 0.55, roughness: 0.46 }),
    floor: new THREE.ShadowMaterial({ color: '#353b38', opacity: 0.17 }),
  }), [])

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updatePreference = () => setReducedMotion(query.matches)
    updatePreference()
    query.addEventListener?.('change', updatePreference)
    return () => query.removeEventListener?.('change', updatePreference)
  }, [])

  useEffect(() => {
    if (!scrollMotion || reducedMotion) return
    const updateScroll = () => { scrollProgress.current = Math.max(0, Math.min(1, window.scrollY / 920)) }
    updateScroll()
    window.addEventListener('scroll', updateScroll, { passive: true })
    return () => window.removeEventListener('scroll', updateScroll)
  }, [scrollMotion, reducedMotion])

  useEffect(() => {
    if (priorOpen.current !== open) {
      wheelTarget.current += open ? -Math.PI * 1.45 : Math.PI * 1.45
      priorOpen.current = open
    }
  }, [open])

  useFrame(({ pointer, clock, camera }, delta) => {
    const response = reducedMotion ? 1 : Math.min(1, delta * 3.2)
    if (scrollMotion && !reducedMotion) {
      const progress = scrollProgress.current
      camera.position.z += ((10.2 - progress * 0.72) - camera.position.z) * Math.min(1, delta * 1.25)
      camera.position.y += ((progress * 0.12) - camera.position.y) * Math.min(1, delta * 1.1)
      camera.lookAt(0, 0, 0)
    }
    if (root.current) {
      const targetY = (!reducedMotion && interactive ? pointer.x * 0.105 : 0) + (open ? -0.035 : 0.018)
      const targetX = !reducedMotion && interactive ? -pointer.y * 0.055 : 0
      root.current.rotation.y += (targetY - root.current.rotation.y) * response
      root.current.rotation.x += (targetX - root.current.rotation.x) * response
      root.current.position.y = reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.46) * 0.045
    }
    if (doorPivot.current) {
      const target = open ? -1.12 : 0
      doorPivot.current.rotation.y += (target - doorPivot.current.rotation.y) * (reducedMotion ? 1 : Math.min(1, delta * 2.3))
    }
    if (wheel.current) {
      wheel.current.rotation.z += (wheelTarget.current - wheel.current.rotation.z) * (reducedMotion ? 1 : Math.min(1, delta * 2.6))
    }
    boltRefs.current.forEach((bolt, index) => {
      if (!bolt) return
      const angle = (index / 8) * Math.PI * 2
      const radius = Math.hypot(bolt.position.x, bolt.position.y)
      const targetRadius = open ? 1.67 : 1.88
      const nextRadius = radius + (targetRadius - radius) * (reducedMotion ? 1 : Math.min(1, delta * 5.2))
      bolt.position.set(Math.cos(angle) * nextRadius, Math.sin(angle) * nextRadius, 0.285)
      bolt.rotation.z = angle + Math.PI / 2
    })
  })

  return (
    <group ref={root}>
      {/* Cast shell: deep, heavy, softly rounded plate steel. */}
      <mesh geometry={bodyGeometry} material={materials.shell} position={[0, 0, 0]} castShadow receiveShadow />
      <mesh geometry={faceGeometry} material={materials.faceDark} position={[0, 0, 0.86]} castShadow receiveShadow />
      <mesh geometry={innerFaceGeometry} material={materials.face} position={[0, 0, 0.99]} castShadow receiveShadow />

      {/* Machined corner fasteners. */}
      {[-1, 1].flatMap((x) => [-1, 1].map((y, index) => (
        <group key={`${x}-${y}-${index}`} position={[x * 2.28, y * 2.28, 1.055]}>
          <mesh geometry={rivetGeometry} material={materials.steel} castShadow />
          <mesh position={[0, 0, 0.042]}>
            <sphereGeometry args={[0.018, 10, 8]} />
            <meshStandardMaterial color="#2b302f" metalness={0.5} roughness={0.38} />
          </mesh>
        </group>
      )))}

      {/* Three-piece forged hinge barrels on the left edge. */}
      {[-1.62, 0, 1.62].map((y) => (
        <group key={y} position={[-2.69, y, 0.91]}>
          <mesh position={[0.02, 0, -0.035]} castShadow>
            <boxGeometry args={[0.34, 0.34, 0.2]} />
            <primitive object={materials.faceDark} attach="material" />
          </mesh>
          <mesh geometry={hingeGeometry} material={materials.steel} castShadow />
          <mesh geometry={hingeCapGeometry} material={materials.brass} position={[0, 0.22, 0]} />
          <mesh geometry={hingeCapGeometry} material={materials.brass} position={[0, -0.22, 0]} />
        </group>
      ))}

      {/* Swinging door, mounted on a physical left-side pivot. */}
      <group ref={doorPivot} position={[-2.39, 0, 1.01]}>
        <group position={[2.39, 0, 0]}>
          <mesh geometry={doorBackingGeometry} rotation={[Math.PI / 2, 0, 0]} material={materials.shellEdge} castShadow receiveShadow />
          <mesh geometry={doorDiscGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0.23]} material={materials.panel} castShadow receiveShadow />
          <mesh geometry={frameRing} position={[0, 0, 0.31]} material={materials.steel} castShadow />
          <mesh geometry={innerRing} position={[0, 0, 0.315]} material={materials.brushed} />

          {/* Fine radial machining marks on the face ring. */}
          {Array.from({ length: 36 }, (_, index) => {
            const angle = (index / 36) * Math.PI * 2
            const major = index % 3 === 0
            const radius = 1.79
            return (
              <mesh
                key={`mark-${index}`}
                position={[Math.cos(angle) * radius, Math.sin(angle) * radius, 0.31]}
                rotation={[0, 0, angle]}
                castShadow={false}
              >
                <boxGeometry args={[major ? 0.12 : 0.065, major ? 0.025 : 0.014, 0.017]} />
                <primitive object={major ? materials.steel : materials.brushed} attach="material" />
              </mesh>
            )
          })}

          {/* Radial locking bolts; their travel is animated by the lock state. */}
          {Array.from({ length: 8 }, (_, index) => (
            <group
              key={`bolt-${index}`}
              ref={(node) => {
                boltRefs.current[index] = node
                if (node && !node.userData.vaultBoltInitialized) {
                  const angle = (index / 8) * Math.PI * 2
                  const radius = open ? 1.67 : 1.88
                  node.position.set(Math.cos(angle) * radius, Math.sin(angle) * radius, 0.285)
                  node.rotation.z = angle + Math.PI / 2
                  node.userData.vaultBoltInitialized = true
                }
              }}
            >
              <mesh geometry={boltGeometry} material={materials.steel} castShadow receiveShadow />
              <mesh position={[0, 0, 0.098]}>
                <boxGeometry args={[0.08, 0.3, 0.02]} />
                <primitive object={materials.brushed} attach="material" />
              </mesh>
            </group>
          ))}

          {/* Recessed dial housing and the turned central wheel. */}
          <mesh geometry={centerDiscGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0.35]} material={materials.recess} castShadow />
          <mesh geometry={hubRing} position={[0, 0, 0.45]} material={materials.brass} castShadow />
          <group ref={wheel} position={[0, 0, 0.46]}>
            {[0, 1, 2, 3].map((index) => {
              const angle = (index * Math.PI) / 2
              return (
                <group key={`spoke-${index}`} rotation={[0, 0, angle]}>
                  <mesh position={[0.43, 0, 0]} castShadow receiveShadow>
                    <boxGeometry args={[0.77, 0.095, 0.075]} />
                    <primitive object={materials.steel} attach="material" />
                  </mesh>
                  <mesh position={[0.82, 0, 0]} castShadow>
                    <sphereGeometry args={[0.105, 20, 16]} />
                    <primitive object={materials.brass} attach="material" />
                  </mesh>
                </group>
              )
            })}
            <mesh geometry={hubGeometry} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0.035]} material={materials.steel} castShadow />
            <mesh position={[0, 0, 0.125]}>
              <sphereGeometry args={[0.09, 28, 20]} />
              <primitive object={materials.brass} attach="material" />
            </mesh>
          </group>
          <mesh position={[0, 0, 0.49]}>
            <torusGeometry args={[0.48, 0.018, 10, 72]} />
            <primitive object={materials.brushed} attach="material" />
          </mesh>
        </group>
      </group>

      {/* Soft studio-floor contact shadow, kept subtle and unobtrusive. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.01, 0.1]} receiveShadow>
        <planeGeometry args={[9.2, 4.4]} />
        <primitive object={materials.floor} attach="material" />
      </mesh>
    </group>
  )
}

export function VaultScene({ open = false, theme = 'light', className = '', interactive = true, scrollMotion = false }: VaultSceneProps) {
  const lightMode = theme === 'light'
  return (
    <div className={`vault-scene ${className}`} aria-label="Three-dimensional steel vault">
      <Canvas
        fallback={<VaultSilhouette className={className} />}
        shadows
        dpr={[1, 1.6]}
        camera={{ position: [0, 0, 10.2], fov: 36, near: 0.1, far: 100 }}
        gl={{ alpha: true, antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.13 }}
        onCreated={({ gl }) => { gl.outputColorSpace = THREE.SRGBColorSpace }}
      >
        <ambientLight intensity={lightMode ? 1.35 : 0.86} />
        <hemisphereLight color="#f8f4e9" groundColor="#4b514e" intensity={lightMode ? 0.78 : 0.55} />
        <directionalLight
          castShadow
          position={[5.3, 7.5, 7.2]}
          intensity={lightMode ? 4.4 : 3.1}
          shadow-mapSize={[1024, 1024]}
          shadow-camera-left={-6}
          shadow-camera-right={6}
          shadow-camera-top={6}
          shadow-camera-bottom={-6}
          shadow-bias={-0.00012}
        />
        <pointLight position={[-4.8, 1.1, 3.4]} intensity={17} color="#d7c39a" distance={12} />
        <pointLight position={[4.5, -1.8, -2.6]} intensity={21} color="#8ca7a3" distance={12} />
        <pointLight position={[0, 5.5, -3.8]} intensity={9} color="#e1e3df" distance={12} />
        <VaultModel open={open} interactive={interactive} scrollMotion={scrollMotion} />
      </Canvas>
    </div>
  )
}
