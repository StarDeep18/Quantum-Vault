const encoder = new TextEncoder()
const decoder = new TextDecoder()
const asBufferSource = (bytes: Uint8Array): BufferSource => bytes as unknown as BufferSource

export const PASSWORD_KDF_ITERATIONS = 600_000

export function randomBytes(length: number): Uint8Array {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error('Secure browser randomness is unavailable. Open Quantum Vault in a secure context.')
  }
  return globalThis.crypto.getRandomValues(new Uint8Array(length))
}

export function toBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }
  return btoa(binary)
}

export function fromBase64(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

export async function derivePasswordWrappingKey(
  password: string,
  salt: Uint8Array,
  iterations = PASSWORD_KDF_ITERATIONS,
): Promise<CryptoKey> {
  const sourceKey = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: asBufferSource(salt), iterations, hash: 'SHA-256' },
    sourceKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export async function importDataKey(rawKey: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', asBufferSource(rawKey), { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
}

export async function encryptBytes(
  key: CryptoKey,
  plaintext: Uint8Array,
  iv: Uint8Array,
  additionalData: string,
): Promise<Uint8Array> {
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: asBufferSource(iv), additionalData: asBufferSource(encoder.encode(additionalData)), tagLength: 128 },
    key,
    asBufferSource(plaintext),
  )
  return new Uint8Array(ciphertext)
}

export async function decryptBytes(
  key: CryptoKey,
  ciphertext: Uint8Array,
  iv: Uint8Array,
  additionalData: string,
): Promise<Uint8Array> {
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: asBufferSource(iv), additionalData: asBufferSource(encoder.encode(additionalData)), tagLength: 128 },
    key,
    asBufferSource(ciphertext),
  )
  return new Uint8Array(plaintext)
}

export async function fingerprintFor(rawKey: Uint8Array): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', asBufferSource(rawKey)))
  return Array.from(digest.slice(0, 8), (byte) => byte.toString(16).padStart(2, '0').toUpperCase())
    .join('')
    .match(/.{1,4}/g)
    ?.join(' · ') || '—'
}

export function encodeText(value: string): Uint8Array {
  return encoder.encode(value)
}

export function decodeText(value: Uint8Array): string {
  return decoder.decode(value)
}
