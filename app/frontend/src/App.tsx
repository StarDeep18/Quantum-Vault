import { useEffect, useState } from 'react'
import type { HardwareStatus, SecretEntry, Theme, VaultRecord, VaultSession } from './types'
import { createVault, saveVaultEntries, unlockVault, vaultStorage } from './services/vaultService'
import { getHardwareStatus } from './services/quantumService'
import { CreateVaultModal } from './components/CreateVaultModal'
import type { VaultDraft } from './components/CreateVaultModal'
import { LandingPage } from './components/LandingPage'
import { LockScreen } from './components/LockScreen'
import { QuantumGeneration } from './components/QuantumGeneration'
import { VaultDashboard } from './components/VaultDashboard'

const defaultHardware = {
  available: false,
  reviewDemoEnabled: false,
  provider: 'hardware',
  label: 'Quantum hardware',
  reason: 'The quantum backend is not connected. No quantum measurements can be requested.',
  connected: false,
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'))
  const [hardware, setHardware] = useState<HardwareStatus>(defaultHardware)
  const [savedVault, setSavedVault] = useState<VaultRecord | null>(null)
  const [record, setRecord] = useState<VaultRecord | null>(null)
  const [session, setSession] = useState<VaultSession | null>(null)
  const [screen, setScreen] = useState<'landing' | 'locked' | 'dashboard'>('landing')
  const [createOpen, setCreateOpen] = useState(false)
  const [generationDraft, setGenerationDraft] = useState<VaultDraft | null>(null)
  const [locking, setLocking] = useState(false)
  const [storageError, setStorageError] = useState('')

  useEffect(() => {
    let active = true
    getHardwareStatus().then((status) => { if (active) setHardware(status) })
    vaultStorage.read()
      .then((saved) => { if (active) setSavedVault(saved) })
      .catch((cause) => {
        if (!active) return
        setStorageError(cause instanceof Error ? cause.message : 'Local vault storage could not be opened.')
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f3f2ee' : '#171a19')
    try { localStorage.setItem('quantum-vault-theme', theme) } catch { /* theme preference is optional */ }
  }, [theme])

  function beginCreate() {
    if (savedVault) {
      setRecord(savedVault)
      setScreen('locked')
      return
    }
    setCreateOpen(true)
  }

  function openSavedVault() {
    if (!savedVault) return
    setRecord(savedVault)
    setScreen('locked')
  }

  function continueToGeneration(draft: VaultDraft) {
    setCreateOpen(false)
    setGenerationDraft(draft)
  }

  function cancelGeneration() {
    setGenerationDraft(null)
  }

  async function sealVault(material: Parameters<typeof createVault>[2]) {
    if (!generationDraft) throw new Error('The vault setup has expired. Start again to create a new vault.')
    const created = await createVault(generationDraft.name, generationDraft.password, material)
    setSavedVault(created.record)
    setRecord(created.record)
    setSession(created.session)
    setGenerationDraft(null)
    setScreen('dashboard')
    setLocking(false)
  }

  async function unlock(password: string): Promise<VaultSession> {
    if (!record) throw new Error('No local vault was found.')
    try {
      return await unlockVault(record, password)
    } catch {
      throw new Error('That password did not unlock this vault. Check it and try again.')
    }
  }

  function completeUnlock(nextSession: VaultSession) {
    setSession(nextSession)
    setScreen('dashboard')
  }

  function lockVault() {
    if (locking) return
    setLocking(true)
    window.setTimeout(() => {
      setSession(null)
      setLocking(false)
      setScreen('locked')
    }, 1120)
  }

  async function saveEntry(entry: SecretEntry) {
    if (!record || !session) throw new Error('The vault is not currently unlocked.')
    const nextEntries = [entry, ...session.entries.filter((current) => current.id !== entry.id)]
    const nextRecord = await saveVaultEntries(record, session.dataKey, nextEntries)
    setRecord(nextRecord)
    setSavedVault(nextRecord)
    setSession({ ...session, entries: nextEntries })
  }

  async function deleteEntry(id: string) {
    if (!record || !session) throw new Error('The vault is not currently unlocked.')
    const nextEntries = session.entries.filter((entry) => entry.id !== id)
    const nextRecord = await saveVaultEntries(record, session.dataKey, nextEntries)
    setRecord(nextRecord)
    setSavedVault(nextRecord)
    setSession({ ...session, entries: nextEntries })
  }

  return (
    <>
      {screen === 'landing' && (
        <>
          <LandingPage
            theme={theme}
            hardware={hardware}
            savedVault={savedVault}
            onThemeChange={setTheme}
            onCreate={beginCreate}
            onOpen={openSavedVault}
          />
          {storageError && <div className="storage-warning" role="status">{storageError}</div>}
          {createOpen && <CreateVaultModal status={hardware} onClose={() => setCreateOpen(false)} onContinue={continueToGeneration} />}
          {generationDraft && (
            <QuantumGeneration
              draft={generationDraft}
              status={hardware}
              onCancel={cancelGeneration}
              onSeal={sealVault}
              onStatusChange={setHardware}
            />
          )}
        </>
      )}
      {screen === 'locked' && record && (
        <LockScreen
          record={record}
          theme={theme}
          onThemeChange={setTheme}
          onUnlock={unlock}
          onOpened={completeUnlock}
          onBack={() => setScreen('landing')}
        />
      )}
      {screen === 'dashboard' && record && session && (
        <VaultDashboard
          record={record}
          session={session}
          theme={theme}
          isLocking={locking}
          onThemeChange={setTheme}
          onLock={lockVault}
          onSaveEntry={saveEntry}
          onDeleteEntry={deleteEntry}
        />
      )}
    </>
  )
}
