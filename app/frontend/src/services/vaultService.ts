import type { KeyMaterial, SecretEntry, VaultRecord, VaultSession } from '../types'
import {
  decodeText,
  decryptBytes,
  derivePasswordWrappingKey,
  encodeText,
  encryptBytes,
  fromBase64,
  importDataKey,
  PASSWORD_KDF_ITERATIONS,
  randomBytes,
  toBase64,
} from './cryptoService'
import { readVaultRecord, removeVaultRecord, writeVaultRecord } from './storageService'

const VAULT_AAD_PREFIX = 'quantum-vault:v1'
const EMPTY_DATA = { schemaVersion: 1, entries: [] as SecretEntry[] }

export const vaultStorage = {
  read: readVaultRecord,
  remove: removeVaultRecord,
}

export async function createVault(
  name: string,
  password: string,
  material: KeyMaterial,
): Promise<{ record: VaultRecord; session: VaultSession }> {
  const rawKey = material.keyBytes
  try {
    if (rawKey.length !== 32) throw new Error('A 256-bit key is required to seal this vault.')
    const vaultId = crypto.randomUUID()
    const salt = randomBytes(16)
    const wrapIv = randomBytes(12)
    const payloadIv = randomBytes(12)
    const wrapKey = await derivePasswordWrappingKey(password, salt, PASSWORD_KDF_ITERATIONS)
    const wrapped = await encryptBytes(wrapKey, rawKey, wrapIv, `${VAULT_AAD_PREFIX}:${vaultId}:wrapped-key`)
    const dataKey = await importDataKey(rawKey)
    const plaintext = encodeText(JSON.stringify(EMPTY_DATA))
    const encryptedPayload = await encryptBytes(
      dataKey,
      plaintext,
      payloadIv,
      `${VAULT_AAD_PREFIX}:${vaultId}:payload`,
    )
    plaintext.fill(0)

    const record: VaultRecord = {
      id: 'primary',
      vaultId,
      name: name.trim(),
      createdAt: new Date().toISOString(),
      source: material.source,
      fingerprint: material.fingerprint,
      kdf: {
        name: 'PBKDF2-SHA-256',
        iterations: PASSWORD_KDF_ITERATIONS,
        salt: toBase64(salt),
      },
      wrappedKey: {
        iv: toBase64(wrapIv),
        ciphertext: toBase64(wrapped),
      },
      payload: {
        iv: toBase64(payloadIv),
        ciphertext: toBase64(encryptedPayload),
      },
    }
    await writeVaultRecord(record)
    return { record, session: { dataKey, entries: [] } }
  } finally {
    // Best-effort clearing: JavaScript cannot guarantee that all engine copies are erased.
    rawKey.fill(0)
  }
}

export async function unlockVault(record: VaultRecord, password: string): Promise<VaultSession> {
  const iterations = Math.min(2_000_000, Math.max(100_000, record.kdf.iterations || PASSWORD_KDF_ITERATIONS))
  const salt = fromBase64(record.kdf.salt)
  const wrapKey = await derivePasswordWrappingKey(password, salt, iterations)
  let rawKey: Uint8Array | null = null
  let plaintext: Uint8Array | null = null
  try {
    rawKey = await decryptBytes(
      wrapKey,
      fromBase64(record.wrappedKey.ciphertext),
      fromBase64(record.wrappedKey.iv),
      `${VAULT_AAD_PREFIX}:${record.vaultId}:wrapped-key`,
    )
    if (rawKey.length !== 32) throw new Error('The stored key envelope is invalid.')
    const dataKey = await importDataKey(rawKey)
    plaintext = await decryptBytes(
      dataKey,
      fromBase64(record.payload.ciphertext),
      fromBase64(record.payload.iv),
      `${VAULT_AAD_PREFIX}:${record.vaultId}:payload`,
    )
    const parsed = JSON.parse(decodeText(plaintext)) as { schemaVersion?: number; entries?: SecretEntry[] }
    if (parsed.schemaVersion !== 1 || !Array.isArray(parsed.entries)) {
      throw new Error('This vault record uses an unsupported format.')
    }
    return { dataKey, entries: parsed.entries }
  } finally {
    rawKey?.fill(0)
    plaintext?.fill(0)
  }
}

export async function saveVaultEntries(
  record: VaultRecord,
  dataKey: CryptoKey,
  entries: SecretEntry[],
): Promise<VaultRecord> {
  const payloadIv = randomBytes(12)
  const plaintext = encodeText(JSON.stringify({ schemaVersion: 1, entries }))
  try {
    const ciphertext = await encryptBytes(
      dataKey,
      plaintext,
      payloadIv,
      `${VAULT_AAD_PREFIX}:${record.vaultId}:payload`,
    )
    const updated: VaultRecord = {
      ...record,
      payload: { iv: toBase64(payloadIv), ciphertext: toBase64(ciphertext) },
    }
    await writeVaultRecord(updated)
    return updated
  } finally {
    plaintext.fill(0)
  }
}
