import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Theme, VaultRecord, VaultSession } from '../types'
import { BrandMark, Icon } from './Icons'
import { ThemeToggle } from './ThemeToggle'
import { VaultScene } from './VaultSceneLazy'

interface LockScreenProps {
  record: VaultRecord
  theme: Theme
  onThemeChange: (theme: Theme) => void
  onUnlock: (password: string) => Promise<VaultSession>
  onOpened: (session: VaultSession) => void
  onBack: () => void
}

type UnlockPhase = 'idle' | 'verifying' | 'opening' | 'error'

export function LockScreen({ record, theme, onThemeChange, onUnlock, onOpened, onBack }: LockScreenProps) {
  const [password, setPassword] = useState('')
  const [phase, setPhase] = useState<UnlockPhase>('idle')
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState('')
  const busy = phase === 'verifying' || phase === 'opening'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!password || busy) return
    setError('')
    setPhase('verifying')
    try {
      const session = await onUnlock(password)
      setPhase('opening')
      setPassword('')
      await new Promise((resolve) => window.setTimeout(resolve, 780))
      onOpened(session)
    } catch (cause) {
      setPhase('error')
      setError(cause instanceof Error ? cause.message : 'This password did not unlock the vault.')
    }
  }

  const sourceLabel = record.source.kind === 'quantum_hardware'
    ? record.source.label
    : record.source.kind === 'review_demo'
      ? record.source.label
      : 'Browser CSPRNG · classical'
  const demoVault = record.source.kind === 'review_demo'

  return (
    <main className={`lock-screen ${phase === 'opening' ? 'lock-screen-opening' : ''}`}>
      <header className="lock-header">
        <button className="brand-lock" type="button" onClick={onBack} aria-label="Back to Quantum Vault introduction">
          <BrandMark size={31} /><span>QUANTUM <b>VAULT</b></span>
        </button>
        <div className="lock-header-right"><span className="local-indicator"><i /> ON THIS DEVICE</span><ThemeToggle theme={theme} onChange={onThemeChange} /></div>
      </header>
      <div className="lock-layout">
        <section className="lock-object-column">
          <div className="lock-object-caption"><span className="eyebrow">LOCAL VAULT / SEALED</span><span className="lock-status-pill"><Icon name="lock" size={13} /> LOCKED</span></div>
          <div className="lock-vault-stage">
            <div className="lock-scene-glow" />
            <VaultScene open={phase === 'opening'} theme={theme} interactive className="lock-vault-scene" />
            <div className="lock-plate"><span><BrandMark size={16} /> QV · 001</span><span>EST. {new Date(record.createdAt).getFullYear()}</span></div>
          </div>
          <div className="lock-fingerprint-card">
            <span className="fingerprint-icon"><Icon name="fingerprint" size={18} /></span>
            <div><span className="section-label">KEY FINGERPRINT</span><strong>{record.fingerprint}</strong></div>
            <span className="fingerprint-check"><Icon name="check" size={15} /></span>
          </div>
        </section>

        <section className="unlock-panel">
          <div className="unlock-panel-top"><span className="eyebrow">{record.name.toUpperCase()} / PRIVATE</span><span className="lock-glyph"><Icon name="lock" size={21} /></span></div>
          <h1>Your vault<br /><em>is locked.</em></h1>
          <p className="unlock-copy">Enter your master password to verify the wrapped key and open your local vault.</p>
          <form onSubmit={submit} className="unlock-form">
            <label className="field-label" htmlFor="unlock-password">Master password</label>
            <div className="password-input-wrap">
              <input id="unlock-password" className={`text-field ${error ? 'field-error' : ''}`} type={visible ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus disabled={busy} placeholder="Your master password" />
              <button type="button" className="field-eye" onClick={() => setVisible((value) => !value)} aria-label={visible ? 'Hide password' : 'Show password'}><Icon name={visible ? 'eye-off' : 'eye'} size={17} /></button>
            </div>
            {error && <p className="inline-error" role="alert">{error}</p>}
            {busy ? (
              <div className="unlock-state" role="status"><span className="progress-spinner" /><div><strong>{phase === 'verifying' ? 'VERIFYING KEY · VAULT' : 'OPENING VAULT'}</strong><small>{phase === 'verifying' ? 'Checking the authenticated key envelope locally.' : 'Mechanical lock released.'}</small></div></div>
            ) : (
              <button className="button button-dark button-wide" type="submit" disabled={!password}>
                OPEN VAULT <Icon name="arrow-right" size={16} />
              </button>
            )}
          </form>
          <div className="unlock-divider" />
          <div className="unlock-details">
            <div><span className="section-label">KEY SOURCE</span><strong className={record.source.kind === 'classical_csprng' ? 'text-classical' : demoVault ? 'text-demo' : ''}>{sourceLabel}</strong></div>
            <div><span className="section-label">ENCRYPTION</span><strong>AES-256-GCM</strong></div>
          </div>
          <p className="lock-privacy-note"><Icon name="shield" size={14} /> The vault is encrypted on this device. The master password is not stored.</p>
        </section>
      </div>
      <div className="lock-bottom-note"><span>{demoVault ? 'REVIEW DEMO · NO LIVE QPU · PREDICTABLE KEY' : 'QUANTUM-GENERATED RANDOMNESS, WHEN CONNECTED'}</span><span>PROTOTYPE · NOT FOR PRODUCTION CREDENTIALS</span></div>
    </main>
  )
}
