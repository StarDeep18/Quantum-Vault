import { useEffect, useMemo, useRef, useState } from 'react'
import type { SecretEntry, Theme, VaultRecord, VaultSession } from '../types'
import { Icon } from './Icons'
import { ThemeToggle } from './ThemeToggle'
import { VaultScene } from './VaultSceneLazy'
import { SecretEditor } from './SecretEditor'

interface VaultDashboardProps {
  record: VaultRecord
  session: VaultSession
  theme: Theme
  isLocking: boolean
  onThemeChange: (theme: Theme) => void
  onLock: () => void
  onSaveEntry: (entry: SecretEntry) => Promise<void>
  onDeleteEntry: (id: string) => Promise<void>
}

type Filter = 'all' | 'password' | 'api-key' | 'secure-note'

export function VaultDashboard({ record, session, theme, isLocking, onThemeChange, onLock, onSaveEntry, onDeleteEntry }: VaultDashboardProps) {
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<SecretEntry | null | undefined>(undefined)
  const [deleteTarget, setDeleteTarget] = useState<SecretEntry | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [revealed, setRevealed] = useState<Record<string, boolean>>({})
  const [copied, setCopied] = useState<string | null>(null)
  const [toast, setToast] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  const counts = useMemo(() => ({
    all: session.entries.length,
    password: session.entries.filter((item) => item.kind === 'password').length,
    'api-key': session.entries.filter((item) => item.kind === 'api-key').length,
    'secure-note': session.entries.filter((item) => item.kind === 'secure-note').length,
  }), [session.entries])

  const visibleEntries = useMemo(() => {
    const query = search.trim().toLowerCase()
    return session.entries
      .filter((entry) => filter === 'all' || entry.kind === filter)
      .filter((entry) => !query || `${entry.title} ${entry.username} ${entry.website} ${entry.notes}`.toLowerCase().includes(query))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  }, [session.entries, search, filter])

  function handleReveal(entry: SecretEntry) {
    const next = !revealed[entry.id]
    setRevealed((current) => ({ ...current, [entry.id]: next }))
    if (next) window.setTimeout(() => setRevealed((current) => ({ ...current, [entry.id]: false })), 20_000)
  }

  async function handleCopy(entry: SecretEntry) {
    const value = entry.kind === 'secure-note' ? entry.notes : entry.secret
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(entry.id)
      setToast('Copied to clipboard')
      window.setTimeout(() => setCopied((current) => current === entry.id ? null : current), 1500)
      window.setTimeout(() => setToast(''), 1900)
    } catch {
      setToast('Clipboard access is unavailable in this browser')
      window.setTimeout(() => setToast(''), 2400)
    }
  }

  async function save(entry: SecretEntry) {
    await onSaveEntry(entry)
    setEditing(undefined)
    setToast('Encrypted and saved')
    window.setTimeout(() => setToast(''), 1700)
  }

  function remove(entry: SecretEntry) {
    setDeleteTarget(entry)
  }

  async function confirmRemove() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await onDeleteEntry(deleteTarget.id)
      setRevealed((current) => { const next = { ...current }; delete next[deleteTarget.id]; return next })
      setDeleteTarget(null)
      setToast('Secret removed')
      window.setTimeout(() => setToast(''), 1700)
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : 'Could not remove this secret')
      window.setTimeout(() => setToast(''), 2200)
    } finally {
      setDeleting(false)
    }
  }

  const sourceLabel = record.source.kind === 'quantum_hardware'
    ? record.source.label
    : record.source.kind === 'review_demo'
      ? record.source.label
      : 'Browser CSPRNG · classical'
  const sourceKindLabel = record.source.kind === 'quantum_hardware'
    ? 'QUANTUM HARDWARE'
    : record.source.kind === 'review_demo'
      ? 'REVIEW DEMO'
      : 'CLASSICAL / SYSTEM CSPRNG'
  const sourceTone = record.source.kind === 'classical_csprng' ? 'text-classical' : record.source.kind === 'review_demo' ? 'text-demo' : ''

  return (
    <main className={`dashboard-shell ${isLocking ? 'dashboard-locking' : ''}`}>
      <header className="app-header dashboard-header">
        <div className="brand-lock" aria-label="Quantum Vault">
          <span className="brand-mark-wrap"><span className="brand-pulse" /><Icon name="disc" size={22} /></span>
          <span>QUANTUM <b>VAULT</b></span>
        </div>
        <div className="dashboard-crumb"><span>LOCAL /</span><strong>{record.name.toUpperCase()}</strong></div>
        <div className="header-actions">
          <span className="local-indicator"><i /> ON THIS DEVICE</span>
          <ThemeToggle theme={theme} onChange={onThemeChange} />
          <button className="button button-outline button-lock" type="button" onClick={onLock} disabled={isLocking}>
            <Icon name="lock" size={15} /> LOCK VAULT
          </button>
        </div>
      </header>

      <div className="dashboard-container">
        <div className="dashboard-title-row">
          <div>
            <div className="eyebrow dashboard-eyebrow"><span className="status-pip" /> THE INNER ROOM <span className="eyebrow-separator">/</span> {record.name.toUpperCase()}</div>
            <h1>Welcome back<span className="title-period">.</span></h1>
          </div>
          <div className="dashboard-title-aside"><span className="mini-engraving"><BrandGlyph /></span><span>PRIVATE BY DESIGN<br /><b>ONLY STORED HERE</b></span></div>
        </div>

        {record.source.kind === 'review_demo' && <div className="review-demo-vault-note" role="status"><Icon name="shield" size={14} /><span><strong>REVIEW DEMO VAULT</strong> · predictable fixture key · do not store real credentials.</span></div>}

        <div className="vault-workspace">
          <section className="object-panel" aria-label="Open vault">
            <div className="object-panel-top"><span className="eyebrow">01 / THE OBJECT</span><span className={`object-open-pill ${isLocking ? 'object-closing' : ''}`}><i /> {isLocking ? 'CLOSING' : 'OPEN'}</span></div>
            <div className="dashboard-scene-wrap">
              <div className="scene-halo" />
              <div className="scene-arc scene-arc-one" /><div className="scene-arc scene-arc-two" />
              <VaultScene open={!isLocking} theme={theme} className="dashboard-vault-scene" />
              <div className="scene-index scene-index-left"><span>QV</span> / 01</div>
              <div className="scene-index scene-index-right">KEYED · AES 256</div>
              <div className="scene-plate"><span>QV / PRIVATE STORAGE</span><span>NO. 001</span></div>
            </div>
            <div className="object-panel-bottom">
              <div className="verified-key"><span className="verified-icon"><Icon name="fingerprint" size={17} /></span><div><span className="section-label">KEY VERIFIED</span><strong>{record.fingerprint}</strong></div><span className="verified-check"><Icon name="check" size={13} /></span></div>
              <div className="object-source"><span className="section-label">SOURCE</span><strong className={sourceTone}>{sourceLabel}</strong></div>
            </div>
          </section>

          <section className="contents-panel" aria-label="Stored secrets">
            <div className="contents-panel-header">
              <div><div className="eyebrow">02 / THE CONTENTS</div><h2>Your secrets <span>{session.entries.length.toString().padStart(2, '0')}</span></h2></div>
              <button className="button button-dark add-secret-button" type="button" onClick={() => setEditing(null)}><Icon name="plus" size={16} /> ADD SECRET</button>
            </div>

            <div className="secret-toolbar">
              <label className="secret-search"><Icon name="search" size={17} /><input ref={searchRef} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a secret" aria-label="Find a secret" /><kbd>⌘ K</kbd></label>
              <button className="toolbar-sort" type="button" onClick={() => setFilter('all')} aria-label="Show all secrets"><Icon name="grid" size={16} /></button>
            </div>

            <nav className="secret-filters" aria-label="Filter secrets">
              {([
                ['all', 'All', counts.all],
                ['password', 'Passwords', counts.password],
                ['api-key', 'API keys', counts['api-key']],
                ['secure-note', 'Notes', counts['secure-note']],
              ] as const).map(([key, label, count]) => (
                <button key={key} type="button" className={filter === key ? 'filter-active' : ''} onClick={() => setFilter(key)}>
                  {label}<span>{count.toString().padStart(2, '0')}</span>
                </button>
              ))}
            </nav>

            <div className="secret-list">
              {visibleEntries.length > 0 ? visibleEntries.map((entry) => (
                <SecretRow
                  key={entry.id}
                  entry={entry}
                  revealed={Boolean(revealed[entry.id])}
                  copied={copied === entry.id}
                  onReveal={() => handleReveal(entry)}
                  onCopy={() => void handleCopy(entry)}
                  onEdit={() => setEditing(entry)}
                  onDelete={() => void remove(entry)}
                />
              )) : (
                <div className="empty-secrets">
                  <span className="empty-seal"><BrandGlyph /></span>
                  <strong>{session.entries.length === 0 ? 'A place for what matters.' : 'Nothing in this section.'}</strong>
                  <p>{session.entries.length === 0 ? 'Your first secret will be encrypted before it is saved.' : 'Try another filter or search term.'}</p>
                  {session.entries.length === 0 && <button className="text-button" type="button" onClick={() => setEditing(null)}>ADD YOUR FIRST SECRET <Icon name="arrow-right" size={14} /></button>}
                </div>
              )}
            </div>

            <div className="security-strip">
              <div className="security-strip-title"><span className="strip-shield"><Icon name="shield" size={16} /></span><span><small>SECURITY STATE</small><strong>ENCRYPTED ON DEVICE</strong></span><span className="secure-live-dot" /></div>
              <div className="security-specs">
                <div><span className="section-label">CIPHER</span><strong>AES-256-GCM</strong></div>
                <div><span className="section-label">PASSWORD KDF</span><strong>PBKDF2 / 600K</strong></div>
                <div><span className="section-label">KEY SOURCE</span><strong className={sourceTone}>{sourceKindLabel}</strong></div>
              </div>
            </div>
          </section>
        </div>
        <footer className="dashboard-footer"><span><Icon name="lock" size={12} /> LOCAL-FIRST · ENCRYPTED BEFORE STORAGE</span><span>PROTOTYPE DEMONSTRATION — NOT FOR PRODUCTION CREDENTIAL STORAGE</span></footer>
      </div>

      {toast && <div className="toast-message" role="status"><Icon name="check" size={14} /> {toast}</div>}
      {editing !== undefined && <SecretEditor entry={editing} onClose={() => setEditing(undefined)} onSave={save} />}
      {deleteTarget && (
        <div className="modal-backdrop" role="presentation">
          <section className="vault-modal delete-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title">
            <span className="delete-emblem"><Icon name="trash" size={19} /></span>
            <p className="eyebrow">REMOVE / PERMANENT</p>
            <h2 id="delete-title">Remove this secret?</h2>
            <p className="modal-intro"><strong>{deleteTarget.title}</strong> will be removed from the encrypted vault. This cannot be undone.</p>
            <div className="delete-actions">
              <button className="button button-outline" type="button" onClick={() => setDeleteTarget(null)} disabled={deleting}>KEEP SECRET</button>
              <button className="button button-delete" type="button" onClick={() => void confirmRemove()} disabled={deleting}>{deleting ? 'REMOVING…' : 'DELETE SECRET'} <Icon name="trash" size={15} /></button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}

function SecretRow({ entry, revealed, copied, onReveal, onCopy, onEdit, onDelete }: {
  entry: SecretEntry
  revealed: boolean
  copied: boolean
  onReveal: () => void
  onCopy: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const icon = entry.kind === 'api-key' ? 'cpu' : entry.kind === 'secure-note' ? 'file' : 'key'
  const value = entry.kind === 'secure-note' ? entry.notes : entry.secret
  const displayValue = revealed ? (value || 'No value stored') : value ? '•'.repeat(14) : 'No value stored'
  const siteLabel = entry.website ? displayWebsite(entry.website) : entry.kind === 'secure-note' ? 'Private note' : 'Saved locally'
  return (
    <article className={`secret-row ${revealed ? 'secret-row-revealed' : ''}`}>
      <div className={`secret-kind-icon kind-${entry.kind}`}><Icon name={icon} size={17} /></div>
      <div className="secret-row-main">
        <div className="secret-title-line"><strong>{entry.title}</strong><span className="secret-kind-label">{entry.kind === 'api-key' ? 'API KEY' : entry.kind === 'secure-note' ? 'SECURE NOTE' : 'PASSWORD'}</span></div>
        <span className="secret-origin">{siteLabel}{entry.username ? ` · ${entry.username}` : ''}</span>
        <span className={`secret-value ${revealed ? 'secret-value-clear' : ''}`}>{displayValue}</span>
      </div>
      <div className="secret-row-actions">
        <button type="button" className="row-action" onClick={onReveal} aria-label={revealed ? 'Hide secret' : 'Reveal secret'} title={revealed ? 'Hide' : 'Reveal'}><Icon name={revealed ? 'eye-off' : 'eye'} size={16} /></button>
        <button type="button" className={`row-action ${copied ? 'action-copied' : ''}`} onClick={onCopy} disabled={!value} aria-label="Copy secret" title={copied ? 'Copied' : 'Copy'}><Icon name={copied ? 'check' : 'copy'} size={16} /></button>
        <button type="button" className="row-action row-action-edit" onClick={onEdit} aria-label="Edit secret" title="Edit"><Icon name="edit" size={15} /></button>
        <button type="button" className="row-action row-action-delete" onClick={onDelete} aria-label="Delete secret" title="Delete"><Icon name="trash" size={15} /></button>
      </div>
    </article>
  )
}

function displayWebsite(raw: string): string {
  try { return new URL(raw.includes('://') ? raw : `https://${raw}`).hostname.replace(/^www\./, '') } catch { return raw }
}

function BrandGlyph() {
  return <span className="brand-glyph"><i /><i /><i /><b /></span>
}
