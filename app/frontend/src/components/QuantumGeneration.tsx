import { useEffect, useRef, useState } from 'react'
import type { KeyMaterial, HardwareStatus } from '../types'
import type { VaultDraft } from './CreateVaultModal'
import { getHardwareStatus, generateClassicalKey, requestQuantumKey, requestReviewDemoKey } from '../services/quantumService'
import { Icon } from './Icons'

interface QuantumGenerationProps {
  draft: VaultDraft
  status: HardwareStatus
  onCancel: () => void
  onSeal: (material: KeyMaterial) => Promise<void>
  onStatusChange: (status: HardwareStatus) => void
}

type Phase = 'ready' | 'requesting' | 'revealing' | 'complete' | 'unavailable' | 'error' | 'sealing'

const EMPTY_WINDOW = '·'.repeat(64)
type MaterialView = Pick<KeyMaterial, 'source' | 'fingerprint' | 'measurementBits'>

export function QuantumGeneration({ draft, status: initialStatus, onCancel, onSeal, onStatusChange }: QuantumGenerationProps) {
  const [status, setStatus] = useState(initialStatus)
  const [phase, setPhase] = useState<Phase>(initialStatus.available || initialStatus.reviewDemoEnabled ? 'ready' : 'unavailable')
  const [progress, setProgress] = useState({ status: 'VAULT READY', detail: 'Choose a real hardware source to begin.' })
  // Keep the 256-bit key bytes out of React state and the rendered tree. Only
  // the separate 64-bit display window and non-secret provenance are stateful.
  const [materialView, setMaterialView] = useState<MaterialView | null>(null)
  const [revealed, setRevealed] = useState(0)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const [selectedSource, setSelectedSource] = useState<'quantum' | 'classical' | 'review-demo' | null>(null)
  const materialRef = useRef<KeyMaterial | null>(null)

  useEffect(() => {
    setStatus(initialStatus)
    setPhase(initialStatus.available || initialStatus.reviewDemoEnabled ? 'ready' : 'unavailable')
  }, [initialStatus])

  useEffect(() => {
    if (phase !== 'revealing' || !materialView) return
    let count = 0
    let timer = 0
    const advance = () => {
      count = Math.min(materialView.measurementBits.length, count + 2)
      setRevealed(count)
      if (count >= materialView.measurementBits.length) {
        timer = window.setTimeout(() => setPhase('complete'), 420)
      } else {
        timer = window.setTimeout(advance, 26)
      }
    }
    timer = window.setTimeout(advance, 220)
    return () => window.clearTimeout(timer)
  }, [phase, materialView])

  useEffect(() => () => {
    materialRef.current?.keyBytes.fill(0)
  }, [])

  async function refreshStatus() {
    setChecking(true)
    const fresh = await getHardwareStatus()
    setStatus(fresh)
    onStatusChange(fresh)
    setPhase(fresh.available || fresh.reviewDemoEnabled ? 'ready' : 'unavailable')
    setError('')
    setChecking(false)
  }

  function setReadyMaterial(next: KeyMaterial) {
    materialRef.current = next
    setMaterialView({
      source: next.source,
      fingerprint: next.fingerprint,
      measurementBits: next.measurementBits,
    })
    setRevealed(0)
    setPhase('revealing')
  }

  async function startQuantum() {
    const reviewDemo = status.reviewDemoEnabled
    if (!reviewDemo && !status.available) return
    setSelectedSource(reviewDemo ? 'review-demo' : 'quantum')
    setError('')
    setProgress(reviewDemo
      ? { status: 'CONNECTING TO QUANTUM FLOW', detail: 'Review demo is enabled; this path will not contact IQM or submit a provider job.' }
      : { status: 'CONNECTING TO QUANTUM BACKEND', detail: 'Sending a 320-shot IQM hardware request; provider acceptance is not yet confirmed.' })
    setPhase('requesting')
    try {
      const onDemoOrHardwareProgress = (next: { status: string; detail: string }) => {
        setProgress({ status: labelForStatus(next.status), detail: next.detail })
      }
      const result = reviewDemo
        ? await requestReviewDemoKey(onDemoOrHardwareProgress)
        : await requestQuantumKey(onDemoOrHardwareProgress, status.jobTimeoutSeconds ?? 3600)
      setReadyMaterial(result)
    } catch (cause) {
      setPhase('error')
      const fallback = reviewDemo ? 'The review demo could not create a demo key.' : 'Quantum measurements were not received. No key was created.'
      setError(cause instanceof Error ? cause.message : fallback)
    }
  }

  async function startClassical() {
    setSelectedSource('classical')
    setError('')
    setProgress({ status: 'SYSTEM CSPRNG', detail: 'Generating a key using browser-provided cryptographic randomness.' })
    setPhase('requesting')
    try {
      const result = await generateClassicalKey()
      setReadyMaterial(result)
    } catch (cause) {
      setPhase('error')
      setError(cause instanceof Error ? cause.message : 'System randomness could not be accessed.')
    }
  }

  async function seal() {
    const sensitiveMaterial = materialRef.current
    if (!sensitiveMaterial) return
    setPhase('sealing')
    try {
      await onSeal(sensitiveMaterial)
      materialRef.current = null
    } catch (cause) {
      materialRef.current?.keyBytes.fill(0)
      materialRef.current = null
      setMaterialView(null)
      setPhase('error')
      setError(cause instanceof Error ? cause.message : 'The encrypted vault could not be saved locally.')
    }
  }

  const isQuantumMaterial = materialView?.source.kind === 'quantum_hardware'
  const isDemoMaterial = materialView?.source.kind === 'review_demo'
  const isDemoModeActive = selectedSource === 'review-demo' || isDemoMaterial || (status.reviewDemoEnabled && selectedSource === null)
  const isClassicalSource = materialView?.source.kind === 'classical_csprng' || selectedSource === 'classical'
  const isBusy = phase === 'requesting' || phase === 'revealing' || phase === 'sealing'
  const bitWindow = materialView ? materialView.measurementBits.slice(0, revealed) : ''

  return (
    <div className="modal-backdrop generation-backdrop" role="presentation">
      <section className="vault-modal generation-modal" role="dialog" aria-modal="true" aria-labelledby="generation-title">
        <div className="generation-topline">
          <span className="modal-kicker"><span className="kicker-mark"><Icon name="disc" size={15} /></span> SEALING / {draft.name.toUpperCase()}</span>
          {!isBusy && <button className="icon-button" type="button" onClick={onCancel} aria-label="Close generation window"><Icon name="x" size={18} /></button>}
        </div>

        <div className="generation-heading-row">
          <div>
            <p className="eyebrow">THE KEY IS NEVER SHOWN</p>
            <h2 id="generation-title">{phase === 'complete' ? (isDemoMaterial ? 'Your demo key is ready.' : 'Your key is ready.') : phase === 'sealing' ? 'Sealing the vault.' : isDemoModeActive ? 'A key, from a review fixture.' : 'A key, from measurement.'}</h2>
            <p className="modal-intro">{phase === 'complete' ? (isDemoMaterial ? 'Deterministic demo material · no live QPU · standard encryption.' : 'A private fingerprint is all you will see.') : isDemoModeActive ? 'A review-only bitstream follows the same visual sequence; it is not quantum-generated.' : 'Randomness is measured first. Standard encryption does the rest.'}</p>
          </div>
          <div className={`generation-orbit ${phase === 'requesting' || phase === 'revealing' ? 'orbit-active' : ''}`} aria-hidden="true">
            <div className="orbit-ring orbit-ring-outer" /><div className="orbit-ring orbit-ring-inner" />
            <span className="orbit-center"><Icon name={phase === 'complete' || phase === 'sealing' ? 'check' : 'key'} size={22} /></span>
            <i className="orbit-pin" />
          </div>
        </div>

        <div className={`source-banner ${isClassicalSource ? 'source-banner-classical' : ''} ${isDemoModeActive ? 'source-banner-demo' : ''}`}>
          <span className={`source-led ${(status.available && selectedSource !== 'classical') || materialView || isDemoModeActive ? 'led-ready' : ''} ${isDemoModeActive ? 'led-demo' : ''}`} />
          <div className="source-banner-copy">
            <span className="source-banner-label">{materialView ? 'KEY MATERIAL SOURCE' : isClassicalSource ? 'SELECTED SOURCE' : isDemoModeActive ? 'SOURCE' : 'HARDWARE SOURCE'}</span>
            <strong>{materialView?.source.label || (selectedSource === 'classical' ? 'Browser CSPRNG · classical' : isDemoModeActive ? 'REVIEW DEMO · simulated flow' : status.label)}</strong>
          </div>
          <span className={`source-state ${isClassicalSource ? 'is-classical' : isDemoModeActive ? 'is-demo' : status.available ? 'is-ready' : 'is-offline'}`}>
            {isClassicalSource ? 'CLASSICAL' : isDemoModeActive ? materialView ? 'DEMO MEASUREMENT' : 'DEMO · NO LIVE QPU' : materialView ? 'MEASURED' : status.available ? 'READY' : 'OFFLINE'}
          </span>
        </div>

        {selectedSource !== 'classical' && (isQuantumMaterial || isDemoMaterial || !materialView) ? (
          <div className={`circuit-strip ${isDemoModeActive ? 'circuit-strip-demo' : ''} ${isDemoModeActive && (phase === 'requesting' || phase === 'revealing') ? 'circuit-strip-demo-active' : ''}`} aria-label={isDemoModeActive ? 'Review demonstration of the circuit; no quantum circuit was submitted' : 'Quantum circuit'}>
            <span className="circuit-state">|0⟩</span><span className="circuit-wire" />
            <span className="circuit-gate">H</span><span className="circuit-wire" />
            <span className="circuit-measure">M</span><span className="circuit-wire" />
            <span className="circuit-output">0 / 1</span>
            <span className="circuit-caption">{isDemoModeActive ? 'DEMO CIRCUIT · VISUAL ONLY' : 'fixed measurement circuit'}</span>
          </div>
        ) : (
          <div className="classical-strip">
            <span className="classical-node"><Icon name="cpu" size={17} /> SYSTEM CSPRNG</span>
            <span className="classical-line" />
            <span className="classical-node"><Icon name="key" size={17} /> 256-BIT KEY</span>
            <span className="classical-line" />
            <span className="classical-node"><Icon name="lock" size={17} /> AES-256-GCM</span>
          </div>
        )}

        <div className={`measurement-board ${isDemoModeActive ? 'measurement-board-demo' : ''} ${phase === 'revealing' || phase === 'complete' ? 'measurement-board-live' : ''}`}>
          <div className="measurement-meta">
            <div><span className="section-label">{materialView ? isDemoMaterial ? 'DEMO MEASUREMENT WINDOW' : 'MEASUREMENT WINDOW' : isDemoModeActive ? 'DEMO MEASUREMENT STREAM' : 'MEASUREMENT STREAM'}</span><small>{materialView ? isDemoMaterial ? '64 deterministic demo bits · not IQM data · excluded from key material' : isQuantumMaterial ? '64 provider-returned outcomes · excluded from key material' : '64 SYSTEM CSPRNG outcomes · excluded from key material' : isDemoModeActive ? 'Deterministic fixture · no live QPU' : 'Awaiting provider-returned outcomes'}</small></div>
            <span className="measurement-count">{materialView ? `${revealed.toString().padStart(2, '0')} / 64` : '— / 64'}</span>
          </div>
          <div className={`bit-window ${materialView ? 'bit-window-revealed' : ''}`} aria-live="polite" aria-label={materialView ? `${isDemoMaterial ? 'Demo bits' : isQuantumMaterial ? 'Measured bits' : 'System CSPRNG bits'} ${bitWindow}` : isDemoModeActive ? 'No demo bits revealed yet' : 'No measurement results received yet'}>
            {(materialView ? (bitWindow + EMPTY_WINDOW).slice(0, 64) : EMPTY_WINDOW).split('').map((bit, index) => (
              <span key={index} className={`bit-cell ${index < revealed ? 'bit-cell-on' : ''} ${bit === '1' && index < revealed ? 'bit-one' : ''}`}>
                {index < revealed ? bit : '·'}
              </span>
            ))}
          </div>
          <div className="measurement-foot">
            <span className={phase === 'requesting' || phase === 'revealing' ? 'pulse-dot' : 'steady-dot'} />
            <span>{phase === 'requesting' ? progress.detail : phase === 'revealing' ? isDemoMaterial ? 'Revealing deterministic demo bits · no provider measurements.' : isQuantumMaterial ? 'Revealing provider-returned outcomes · key bits remain sealed.' : 'Revealing system CSPRNG outcomes · classical source.' : phase === 'complete' ? isDemoMaterial ? 'DEMO DATA · displayed progressively · not returned by IQM.' : isQuantumMaterial ? 'Provider-returned outcomes · displayed progressively.' : 'SYSTEM CSPRNG · classical outcomes displayed progressively.' : isDemoModeActive ? 'DEMO · NO LIVE QPU. Choose the review flow to reveal the fixture.' : 'No measurements are shown until a source returns them.'}</span>
          </div>
        </div>

        {phase === 'complete' && materialView && (
          <div className="fingerprint-row">
            <span className="fingerprint-icon"><Icon name="fingerprint" size={17} /></span>
            <div className="fingerprint-copy"><span className="section-label">KEY FINGERPRINT</span><strong>{materialView.fingerprint}</strong></div>
            <div className="fingerprint-meta"><span>256 BITS</span><span>{materialView.source.kind === 'quantum_hardware' ? materialView.source.backend : materialView.source.kind === 'review_demo' ? 'REVIEW DEMO' : 'SYSTEM CSPRNG'}</span></div>
          </div>
        )}

        {(phase === 'unavailable' || phase === 'error') && (
          <div className="hardware-message" role="status">
            <span className="hardware-message-icon"><Icon name="wifi" size={18} /></span>
            <div>
              <strong>{phase === 'error' ? (isDemoModeActive ? 'No demo key was created.' : 'No quantum key was created.') : 'QUANTUM HARDWARE UNAVAILABLE — no quantum key was created.'}</strong>
              <p>{phase === 'error' ? error : status.reason || 'Connect and verify a real IQM quantum processor before requesting measurements.'}</p>
              {status.setupHint && phase === 'unavailable' && <details><summary>Hardware setup</summary><p>{status.setupHint}</p>{status.setupSteps?.length ? <ol>{status.setupSteps.map((step) => <li key={step}>{step}</li>)}</ol> : null}</details>}
            </div>
          </div>
        )}

        {phase === 'complete' && materialView?.source.kind === 'classical_csprng' && (
          <p className="classical-disclaimer"><Icon name="shield" size={15} /> This vault uses classical system randomness. It is not quantum-generated.</p>
        )}
        {phase === 'complete' && isDemoMaterial && (
          <p className="demo-disclaimer"><Icon name="shield" size={15} /> REVIEW DEMO · deterministic fixture · no live QPU. Do not use this demo key for real secrets.</p>
        )}

        <div className="generation-actions">
          {phase === 'unavailable' && (
            <>
              <button type="button" className="button button-dark button-wide" onClick={startClassical}>
                USE CLASSICAL / SYSTEM CSPRNG <Icon name="arrow-right" size={16} />
              </button>
              <div className="generation-action-note">Explicit opt-in · classical CSPRNG · not quantum</div>
              <button type="button" className="text-button" onClick={refreshStatus} disabled={checking}>
                {checking ? 'CHECKING…' : 'CHECK HARDWARE CONNECTION'}
              </button>
            </>
          )}
          {phase === 'ready' && (
            <>
              <button type="button" className="button button-dark button-wide" onClick={startQuantum}>
                {isDemoModeActive ? 'RUN 320-BIT REVIEW DEMO' : 'REQUEST 320 MEASUREMENTS'} <Icon name="arrow-right" size={16} />
              </button>
              <p className="generation-action-note">{isDemoModeActive ? 'DEMO · NO LIVE QPU · deterministic 256-bit demo key + separate 64-bit display.' : '256 bits for the key · 64 separate outcomes for this display.'}</p>
              <button type="button" className="text-button" onClick={startClassical}>Use CLASSICAL / SYSTEM CSPRNG instead</button>
            </>
          )}
          {phase === 'requesting' && (
            <div className="generation-progress" role="status">
              <span className="progress-spinner" />
              <div><strong>{progress.status}</strong><small>{progress.detail}</small></div>
            </div>
          )}
          {phase === 'revealing' && (
            <div className="generation-progress" role="status">
              <span className="progress-spinner" />
              <div><strong>{isDemoMaterial ? 'DEMO KEY MATERIAL ACQUIRED' : isQuantumMaterial ? 'QUANTUM ENTROPY ACQUIRED' : 'SYSTEM RANDOMNESS ACQUIRED'}</strong><small>{isDemoMaterial ? '256 deterministic demo bits reserved. The visible 64-bit demo window is separate; no QPU was used.' : '256 bits reserved as key material. The visible stream is a separate sample.'}</small></div>
            </div>
          )}
          {phase === 'complete' && (
            <>
              {isDemoMaterial && <p className="generation-action-note demo-fingerprint-note">KEY FINGERPRINT CREATED · REVIEW DEMO</p>}
              <button type="button" className="button button-dark button-wide" onClick={seal}>
                SEAL VAULT <Icon name="lock" size={16} />
              </button>
            </>
          )}
          {phase === 'sealing' && (
            <div className="generation-progress" role="status">
              <span className="progress-spinner" />
              <div><strong>ENCRYPTING LOCAL VAULT</strong><small>Wrapping key material and saving authenticated ciphertext on this device.</small></div>
            </div>
          )}
          {phase === 'error' && (
            <>
              <button type="button" className="button button-dark button-wide" onClick={status.reviewDemoEnabled || status.available ? startQuantum : startClassical}>
                {status.reviewDemoEnabled ? 'RETRY REVIEW DEMO' : status.available ? 'RETRY HARDWARE REQUEST' : 'USE CLASSICAL / SYSTEM CSPRNG'} <Icon name="arrow-right" size={16} />
              </button>
              {!status.reviewDemoEnabled && status.available && <button type="button" className="text-button" onClick={startClassical}>Use CLASSICAL / SYSTEM CSPRNG instead</button>}
              <button type="button" className="text-button" onClick={onCancel}>CANCEL</button>
            </>
          )}
        </div>

        <div className="generation-security-note"><span><Icon name="lock" size={13} /> STANDARD AES-256-GCM ENCRYPTION</span><span>PBKDF2-SHA-256 / 600K</span></div>
      </section>
    </div>
  )
}

function labelForStatus(status: string): string {
  switch (status) {
    case 'DEMO_CONNECTING': return 'REVIEW DEMO INITIALIZING'
    case 'DEMO_SUBMITTING': return 'DEMO · CIRCUIT SUBMISSION STAGE'
    case 'DEMO_WAITING': return 'DEMO · PRESENTING QPU WAIT PHASE'
    case 'DEMO_RUNNING': return 'DEMO · SIMULATING QPU RESPONSE'
    case 'DEMO_MEASUREMENTS': return 'DEMO MEASUREMENTS RECEIVED'
    case 'DEMO_PROCESSING': return 'PROCESSING 320 DEMO BITS'
    case 'DEMO_KEY_READY': return 'DEMO KEY MATERIAL READY'
    case 'CONNECTING_TO_BACKEND': return 'CONNECTING TO QUANTUM BACKEND'
    case 'CREATED': return 'JOB CREATED'
    case 'VALIDATING': return 'VALIDATING CIRCUIT'
    case 'SUBMITTING': return 'SUBMITTING TO IQM'
    case 'SUBMITTED': return 'IQM ACCEPTED THE JOB'
    case 'QUEUED': return 'WAITING IN IQM QUEUE'
    case 'RUNNING': return 'MEASURING ON IQM HARDWARE'
    case 'FETCHING_RESULT': return 'FETCHING PROVIDER RESULT'
    case 'COMPLETED': return 'MEASUREMENTS RECEIVED'
    default: return status.replace(/_/g, ' ')
  }
}
