import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { SecretEntry, SecretKind } from '../types'
import { Icon } from './Icons'

interface SecretEditorProps {
  entry: SecretEntry | null
  onClose: () => void
  onSave: (entry: SecretEntry) => Promise<void>
}

export function SecretEditor({ entry, onClose, onSave }: SecretEditorProps) {
  const [kind, setKind] = useState<SecretKind>(entry?.kind || 'password')
  const [title, setTitle] = useState(entry?.title || '')
  const [username, setUsername] = useState(entry?.username || '')
  const [website, setWebsite] = useState(entry?.website || '')
  const [secret, setSecret] = useState(entry?.secret || '')
  const [notes, setNotes] = useState(entry?.notes || '')
  const [visible, setVisible] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setKind(entry?.kind || 'password')
    setTitle(entry?.title || '')
    setUsername(entry?.username || '')
    setWebsite(entry?.website || '')
    setSecret(entry?.secret || '')
    setNotes(entry?.notes || '')
  }, [entry])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    setError('')
    const now = new Date().toISOString()
    try {
      await onSave({
        id: entry?.id || crypto.randomUUID(),
        kind,
        title: title.trim(),
        username: username.trim(),
        website: website.trim(),
        secret: kind === 'secure-note' ? '' : secret,
        notes: notes.trim(),
        createdAt: entry?.createdAt || now,
        updatedAt: now,
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save this item to the encrypted vault.')
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) onClose() }}>
      <section className="vault-modal secret-editor-modal" role="dialog" aria-modal="true" aria-labelledby="secret-editor-title">
        <button className="icon-button modal-close" type="button" onClick={onClose} disabled={saving} aria-label="Close editor"><Icon name="x" size={18} /></button>
        <div className="modal-kicker"><span className="kicker-mark"><Icon name="key" size={14} /></span> ENCRYPTED ITEM</div>
        <h2 id="secret-editor-title">{entry ? 'Edit secret.' : 'Add a secret.'}</h2>
        <p className="modal-intro">Saved encrypted inside {entry ? 'your' : 'the'} local vault.</p>

        <form className="vault-form" onSubmit={submit}>
          <div className="secret-kind-picker" role="group" aria-label="Secret type">
            <button type="button" className={kind === 'password' ? 'kind-active' : ''} onClick={() => setKind('password')}><Icon name="key" size={15} /> Password</button>
            <button type="button" className={kind === 'api-key' ? 'kind-active' : ''} onClick={() => setKind('api-key')}><Icon name="cpu" size={15} /> API key</button>
            <button type="button" className={kind === 'secure-note' ? 'kind-active' : ''} onClick={() => setKind('secure-note')}><Icon name="file" size={15} /> Secure note</button>
          </div>

          <label className="field-label" htmlFor="secret-title">Name</label>
          <input id="secret-title" className="text-field" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={72} required autoFocus placeholder={kind === 'secure-note' ? 'e.g. Recovery codes' : 'e.g. GitHub'} />

          {kind !== 'secure-note' && (
            <>
              {kind === 'password' && (
                <>
                  <label className="field-label" htmlFor="secret-username">Username / email</label>
                  <input id="secret-username" className="text-field" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" placeholder="name@example.com" />
                </>
              )}
              <label className="field-label" htmlFor="secret-website">Website</label>
              <input id="secret-website" className="text-field" value={website} onChange={(event) => setWebsite(event.target.value)} autoComplete="url" placeholder="https://" />
              <label className="field-label" htmlFor="secret-value">{kind === 'api-key' ? 'API key' : 'Password'}</label>
              <div className="password-input-wrap">
                <input id="secret-value" className="text-field" type={visible ? 'text' : 'password'} value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="off" placeholder={kind === 'api-key' ? 'Paste key value' : 'Enter password'} />
                <button type="button" className="field-eye" onClick={() => setVisible((value) => !value)} aria-label={visible ? 'Hide secret' : 'Show secret'}><Icon name={visible ? 'eye-off' : 'eye'} size={17} /></button>
              </div>
            </>
          )}

          <label className="field-label" htmlFor="secret-notes">{kind === 'secure-note' ? 'Note' : 'Notes'} <span className="field-hint">OPTIONAL</span></label>
          <textarea id="secret-notes" className="text-field text-area" value={notes} onChange={(event) => setNotes(event.target.value)} rows={kind === 'secure-note' ? 5 : 3} placeholder={kind === 'secure-note' ? 'Write a note only you can open…' : 'A detail worth remembering…'} />

          {error && <p className="inline-error">{error}</p>}
          <button className="button button-dark button-wide" type="submit" disabled={!title.trim() || saving}>
            {saving ? 'ENCRYPTING…' : entry ? 'SAVE CHANGES' : 'SAVE TO VAULT'} <Icon name="lock" size={15} />
          </button>
          <p className="modal-footnote"><Icon name="shield" size={13} /> Entry contents are encrypted before they leave the editor.</p>
        </form>
      </section>
    </div>
  )
}
