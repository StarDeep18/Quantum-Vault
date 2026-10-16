import type { VaultRecord } from '../types'

const DATABASE = 'quantum-vault-local'
const STORE = 'vaults'
const FALLBACK_KEY = 'quantum-vault:encrypted-record:v1'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) {
      reject(new Error('IndexedDB is not available in this browser.'))
      return
    }
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Could not open local vault storage.'))
    request.onblocked = () => reject(new Error('Local vault storage is blocked by another browser tab.'))
  })
}

export async function readVaultRecord(): Promise<VaultRecord | null> {
  if (!globalThis.indexedDB) {
    const raw = localStorage.getItem(FALLBACK_KEY)
    return raw ? JSON.parse(raw) as VaultRecord : null
  }
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readonly')
      const request = transaction.objectStore(STORE).get('primary') as IDBRequest<VaultRecord | undefined>
      request.onsuccess = () => resolve(request.result ?? null)
      request.onerror = () => reject(request.error || new Error('Could not read the local vault.'))
    })
  } finally {
    db.close()
  }
}

export async function writeVaultRecord(record: VaultRecord): Promise<void> {
  if (!globalThis.indexedDB) {
    localStorage.setItem(FALLBACK_KEY, JSON.stringify(record))
    return
  }
  const db = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite')
      transaction.objectStore(STORE).put(record)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error || new Error('Could not save the encrypted vault.'))
      transaction.onabort = () => reject(transaction.error || new Error('Saving the encrypted vault was aborted.'))
    })
  } finally {
    db.close()
  }
}

export async function removeVaultRecord(): Promise<void> {
  if (!globalThis.indexedDB) {
    localStorage.removeItem(FALLBACK_KEY)
    return
  }
  const db = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite')
      transaction.objectStore(STORE).delete('primary')
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error || new Error('Could not remove the local vault.'))
      transaction.onabort = () => reject(transaction.error || new Error('Removing the local vault was aborted.'))
    })
  } finally {
    db.close()
  }
}
