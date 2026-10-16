export type Theme = 'light' | 'dark'

export type SecretKind = 'password' | 'api-key' | 'secure-note'

export interface SecretEntry {
  id: string
  kind: SecretKind
  title: string
  username: string
  website: string
  secret: string
  notes: string
  createdAt: string
  updatedAt: string
}

export type KeySource =
  | {
      kind: 'quantum_hardware'
      label: string
      provider: string
      backend: string
      providerJobId: string
      generatedAt: string
    }
  | {
      kind: 'classical_csprng'
      label: string
      generatedAt: string
    }
  | {
      kind: 'review_demo'
      label: string
      generatedAt: string
    }

export interface VaultRecord {
  id: 'primary'
  vaultId: string
  name: string
  createdAt: string
  source: KeySource
  fingerprint: string
  kdf: {
    name: 'PBKDF2-SHA-256'
    iterations: number
    salt: string
  }
  wrappedKey: {
    iv: string
    ciphertext: string
  }
  payload: {
    iv: string
    ciphertext: string
  }
}

export interface VaultSession {
  dataKey: CryptoKey
  entries: SecretEntry[]
}

export interface KeyMaterial {
  keyBytes: Uint8Array
  measurementBits: string
  source: KeySource
  fingerprint: string
}

export interface HardwareBackendStatus {
  name: string
  simulator: boolean
  operational: boolean
  qubits?: number | null
  pendingJobs?: number | null
  statusMessage?: string | null
}

export interface HardwareStatus {
  available: boolean
  reviewDemoEnabled: boolean
  provider: string
  label: string
  backend?: string
  backends?: HardwareBackendStatus[]
  jobTimeoutSeconds?: number
  reason: string | null
  setupHint?: string
  setupSteps?: string[]
  connected: boolean
}
