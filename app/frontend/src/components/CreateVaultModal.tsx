import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import type { HardwareStatus } from '../types'
import { Icon } from './Icons'

export interface VaultDraft {
  name: string
  password: string
}

interface CreateVaultModalProps {
  status: HardwareStatus
  onClose: () => void
  onContinue: (draft: VaultDraft) => void
}

function strengthFor(password: string): { score: number; label: string } {
  if (!password) return { score: 0, label: 'Not set' }
  let score = 0
  if (password.length >= 10) score += 1
  if (password.length >= 14) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password)) score += 1
  if (/[^a-zA-Z0-9]/.test(password)) score += 1
  if (score <= 1) return { score: 1, label: 'Add more variety' }
  if (score <= 3) return { score: 2, label: 'Getting stronger' }
  return { score: 3, label: 'Strong passphrase' }
}

export function CreateVaultModal({ status, onClose, onContinue }: CreateVaultModalProps) {
  const [name, setName] = useState('My private vault')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [visible, setVisible] = useState(false)
  const [touched, setTouched] = useState(false)
  const strength = useMemo(() => strengthFor(password), [password])
  const mismatch = Boolean(confirm) && confirm !== password
  const valid = name.trim().length > 0 && password.length >= 10 && confirm === password

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    if (!valid) return
    onContinue({ name: name.trim(), password })
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="vault-modal create-modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
        <button className="icon-button modal-close" type="button" onClick={onClose} aria-label="Close">
          <Icon name="x" size={18} />
        </button>
        <div className="modal-kicker"><span className="kicker-mark"><Icon name="disc" size={15} /></span> LOCAL / DEVICE-BOUND</div>
        <h2 id="create-title">Create your vault.</h2>
        <p className="modal-intro">A private place for the things you cannot afford to lose.</p>

        <form className="vault-form" onSubmit={submit}>
          <label className="field-label" htmlFor="vault-name">Vault name</label>
          <input
            id="vault-name"
            className="text-field"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={48}
            autoComplete="off"
            placeholder="e.g. Personal"
          />

          <div className="field-row-label">
            <label className="field-label" htmlFor="master-password">Master password</label>
            <span className="field-hint">10+ characters</span>
          </div>
          <div className="password-input-wrap">
            <input
              id="master-password"
              className="text-field"
              type={visible ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={10}
              required
              placeholder="Create a long, unique passphrase"
            />
            <button type="button" className="field-eye" onClick={() => setVisible((value) => !value)} aria-label={visible ? 'Hide password' : 'Show password'}>
              <Icon name={visible ? 'eye-off' : 'eye'} size={17} />
            </button>
          </div>
          <div className={`strength-meter strength-${strength.score}`} aria-live="polite">
            <div className="strength-bars"><i /><i /><i /></div>
            <span>{strength.label}</span>
          </div>

          <label className="field-label" htmlFor="confirm-password">Confirm password</label>
          <input
            id="confirm-password"
            className={`text-field ${mismatch ? 'field-error' : ''}`}
            type={visible ? 'text' : 'password'}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
            required
            placeholder="Enter it once more"
          />
          {mismatch && <p className="inline-error">Those passwords do not match.</p>}
          {touched && password.length > 0 && password.length < 10 && <p className="inline-error">Use at least 10 characters.</p>}

          <div className="readiness-list">
            <div className="readiness-item"><span className="readiness-check"><Icon name="check" size={13} /></span><span>AES-256-GCM encryption</span><small>READY</small></div>
            <div className="readiness-item"><span className={`readiness-dot ${status.reviewDemoEnabled || status.available ? 'is-ready' : 'is-offline'}`} /><span>{status.reviewDemoEnabled ? 'Review key source' : 'Quantum entropy source'}</span><small className={status.reviewDemoEnabled || status.available ? 'tone-ready' : 'tone-muted'}>{status.reviewDemoEnabled ? 'DEMO MODE' : status.available ? 'CONNECTED' : 'NOT CONNECTED'}</small></div>
          </div>
          {status.reviewDemoEnabled ? (
            <p className="quiet-note demo-note">DEMO · NO LIVE QPU. Deterministic review bits only; do not store real credentials in a demo vault.</p>
          ) : !status.available ? (
            <p className="quiet-note">You can connect real hardware in the next step, or explicitly choose a classical system source for this vault.</p>
          ) : null}
          <button className="button button-dark button-wide" type="submit" disabled={!valid}>
            CONTINUE TO KEY GENERATION <Icon name="arrow-right" size={16} />
          </button>
          <p className="modal-footnote"><Icon name="lock" size={13} /> Your master password never leaves this device.</p>
        </form>
      </section>
    </div>
  )
}
