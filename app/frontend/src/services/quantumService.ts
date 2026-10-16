import type { HardwareStatus, KeyMaterial, KeySource } from '../types'
import { fingerprintFor } from './cryptoService'

const API = '/api/qrng'
const KEY_BITS = 256
const DISPLAY_BITS = 64
const REQUEST_SHOTS = KEY_BITS + DISPLAY_BITS
const FRONTEND_REVIEW_DEMO_ENABLED = import.meta.env.VITE_QUANTUM_REVIEW_DEMO?.trim().toLowerCase() === 'true'

export type JobProgress = {
  status: string
  detail: string
  provider?: string
  backend?: string
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json() as { error?: { message?: string; hint?: string } }
    return body.error?.hint || body.error?.message || `Request failed (${response.status})`
  } catch {
    return `Request failed (${response.status})`
  }
}

export async function getHardwareStatus(): Promise<HardwareStatus> {
  try {
    const response = await fetch(`${API}/config`, { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`Quantum backend responded with ${response.status}`)
    const body = await response.json() as {
      hardware?: {
        available?: boolean
        provider?: string
        label?: string
        reason?: string | null
        setup_hint?: string
        setup_steps?: string[]
      }
      limits?: { job_timeout_s?: number }
      review_demo_enabled?: boolean
    }
    const hardware = body.hardware ?? {}
    const provider = hardware.provider || 'hardware'
    const reviewDemoEnabled = FRONTEND_REVIEW_DEMO_ENABLED || body.review_demo_enabled === true
    const base = {
      provider,
      label: hardware.label || 'Quantum hardware',
      reason: hardware.reason ?? null,
      setupHint: hardware.setup_hint,
      setupSteps: hardware.setup_steps,
      jobTimeoutSeconds: typeof body.limits?.job_timeout_s === 'number' ? body.limits.job_timeout_s : undefined,
      connected: true,
      reviewDemoEnabled,
    }

    if (reviewDemoEnabled) {
      return {
        ...base,
        available: false,
        provider: 'review_demo',
        label: 'REVIEW DEMO · simulated flow',
        reason: 'DEMO · NO LIVE QPU. This mode uses a deterministic review fixture and submits no provider job.',
        connected: true,
      }
    }

    if (!hardware.available) {
      return {
        ...base,
        available: false,
        reason: hardware.reason || 'IQM hardware credentials are not configured. No quantum key can be created.',
      }
    }

    // This standalone vault is explicitly an IQM-hardware path. Do not allow
    // the backend's alternative provider selection to silently change sources.
    if (provider.toLowerCase() !== 'iqm') {
      return {
        ...base,
        available: false,
        reason: `This vault requires IQM hardware, but the active provider is ${provider}. No provider switch or quantum key was created.`,
      }
    }

    const backendResponse = await fetch(`${API}/backends`, { headers: { Accept: 'application/json' } })
    if (!backendResponse.ok) {
      const detail = await readError(backendResponse)
      return {
        ...base,
        available: false,
        reason: `Live IQM QPU discovery failed: ${detail}. No quantum key can be created.`,
      }
    }
    const discovery = await backendResponse.json() as {
      available?: boolean
      reason?: string | null
      selected_backend?: string | null
      selection_error?: string | null
      backends?: Array<{
        name?: string
        simulator?: boolean
        operational?: boolean
        qubits?: number | null
        pending_jobs?: number | null
        status_message?: string | null
      }>
    }
    const backends = (discovery.backends ?? []).map((backend) => ({
      name: backend.name || 'Unknown QPU',
      simulator: Boolean(backend.simulator),
      operational: Boolean(backend.operational),
      qubits: backend.qubits,
      pendingJobs: backend.pending_jobs,
      statusMessage: backend.status_message,
    }))
    const realBackends = backends.filter((backend) =>
      !backend.simulator && !backend.name.toLowerCase().endsWith(':mock'),
    )
    // Use the provider-reported AUTO choice or pinned QPU, not a client-side
    // guess. Never label the provider online from configuration alone.
    const selected = discovery.selected_backend
      ? realBackends.find((backend) => backend.name === discovery.selected_backend)
      : realBackends[0]
    const available = Boolean(discovery.available && !discovery.selection_error && selected?.operational)
    let reason: string | null = null
    if (!discovery.available) {
      reason = `${discovery.reason || 'IQM could not discover a QPU.'} No quantum key can be created.`
    } else if (discovery.selection_error) {
      reason = `${discovery.selection_error} No quantum key can be created.`
    } else if (!selected && discovery.selected_backend) {
      reason = 'The configured IQM QPU was not present in live discovery. No quantum key can be created.'
    } else if (!selected) {
      reason = 'IQM reported no real QPUs; simulators are not eligible for vault keys. No quantum key can be created.'
    } else if (!selected.operational) {
      reason = `${selected.name} is not reported operational${selected.statusMessage ? `: ${selected.statusMessage}` : ''}. No quantum key can be created.`
    }

    return {
      ...base,
      available,
      backend: selected?.name,
      backends,
      label: selected ? `${base.label} · ${selected.name}` : base.label,
      reason,
    }
  } catch {
    return {
      available: false,
      reviewDemoEnabled: FRONTEND_REVIEW_DEMO_ENABLED,
      provider: FRONTEND_REVIEW_DEMO_ENABLED ? 'review_demo' : 'iqm',
      label: FRONTEND_REVIEW_DEMO_ENABLED ? 'REVIEW DEMO · simulated flow' : 'IQM Quantum Hardware',
      reason: FRONTEND_REVIEW_DEMO_ENABLED
        ? 'DEMO · NO LIVE QPU. The deterministic review fixture can run without the backend.'
        : 'The quantum backend or IQM provider could not be reached. No quantum key was created.',
      connected: false,
    }
  }
}

export async function requestQuantumKey(
  onProgress: (progress: JobProgress) => void,
  timeoutSeconds = 3600,
): Promise<KeyMaterial> {
  type QuantumJob = {
    experiment_id?: string
    job_id?: string
    status?: string
    status_detail?: string | null
    provider?: string | null
    provider_job_id?: string | null
    backend?: string | null
    mode?: string | null
    source?: string | null
    shots?: number | null
  }
  const knownStates = new Set([
    'CREATED', 'VALIDATING', 'SUBMITTING', 'SUBMITTED', 'QUEUED', 'RUNNING',
    'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RATE_LIMITED',
  ])
  const verifyJob = (snapshot: QuantumJob) => {
    if (
      snapshot.mode !== 'hardware'
      || snapshot.source !== 'quantum_hardware'
      || snapshot.shots !== REQUEST_SHOTS
      || snapshot.provider?.toLowerCase() !== 'iqm'
    ) {
      throw new Error('The backend did not confirm an IQM hardware job with exactly 320 shots. No key was created.')
    }
    if (!snapshot.status || !knownStates.has(snapshot.status)) {
      throw new Error('The backend returned an unknown job state. No key was created.')
    }
  }

  onProgress({
    status: 'CONNECTING_TO_BACKEND',
    detail: 'Sending an IQM hardware-mode request for exactly 320 shots; provider acceptance is not yet confirmed.',
  })
  const submit = await fetch(`${API}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ shots: REQUEST_SHOTS, mode: 'hardware', backend: 'auto' }),
  })
  if (!submit.ok) throw new Error(await readError(submit))
  let current = await submit.json() as QuantumJob
  verifyJob(current)
  const jobId = current.experiment_id || current.job_id
  if (!jobId) throw new Error('The quantum backend did not return a measurement job ID. No key was created.')

  const startedAt = Date.now()
  const timeoutMs = Math.max(10, Math.min(86_400, Math.floor(timeoutSeconds))) * 1000
  const terminal = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RATE_LIMITED'])
  while (!terminal.has(current.status!)) {
    const status = current.status!
    onProgress({
      status,
      detail: current.status_detail || describeStatus(status),
      provider: current.provider || undefined,
      backend: current.backend || undefined,
    })
    if (Date.now() - startedAt > timeoutMs) {
      const waitMinutes = Math.ceil(timeoutMs / 60_000)
      throw new Error(`The IQM hardware job is still pending after ${waitMinutes} minutes. Its measurements have not been received, so no key was created.`)
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1800))
    const response = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}`, { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(await readError(response))
    current = await response.json() as QuantumJob
    verifyJob(current)
  }

  if (current.status !== 'COMPLETED') {
    throw new Error(current.status_detail || `The IQM hardware job ended with status ${current.status}. No key was created.`)
  }

  onProgress({ status: 'FETCHING_RESULT', detail: 'The provider job is complete; retrieving its normalized shot-ordered result from the backend.' })
  const resultResponse = await fetch(`${API}/jobs/${encodeURIComponent(jobId)}/result`, { headers: { Accept: 'application/json' } })
  if (!resultResponse.ok) throw new Error(await readError(resultResponse))
  const result = await resultResponse.json() as {
    status?: string
    mode?: string | null
    source?: string | null
    shots?: number | null
    bits?: string
    provider?: string | null
    provider_job_id?: string | null
    backend?: string | null
  }
  if (
    result.status !== 'COMPLETED'
    || result.mode !== 'hardware'
    || result.source !== 'quantum_hardware'
    || result.shots !== REQUEST_SHOTS
    || result.provider?.toLowerCase() !== 'iqm'
  ) {
    throw new Error('The result did not confirm completed IQM hardware provenance for 320 shots. No key was created.')
  }
  if (!result.provider_job_id || !result.backend) {
    throw new Error('The provider result is missing its IQM job ID or QPU name. No key was created.')
  }
  if (
    (current.provider_job_id && current.provider_job_id !== result.provider_job_id)
    || (current.backend && current.backend !== result.backend)
  ) {
    throw new Error('The provider result provenance did not match the completed job. No key was created.')
  }

  const bits = result.bits || ''
  if (bits.length !== REQUEST_SHOTS || !/^[01]{320}$/.test(bits)) {
    throw new Error('The IQM result did not contain exactly 320 valid provider-returned bits. No key was created.')
  }

  // The first 256 provider-returned outcomes become local key material.
  // The final 64 are the separate, visibly progressive measurement window.
  const keyBytes = bitsToBytes(bits.slice(0, KEY_BITS))
  const measurementBits = bits.slice(KEY_BITS, REQUEST_SHOTS)
  const provider = result.provider
  const backend = result.backend
  const label = `${providerLabel(provider)} · ${backend}`
  const source: KeySource = {
    kind: 'quantum_hardware',
    label,
    provider,
    backend,
    providerJobId: result.provider_job_id,
    generatedAt: new Date().toISOString(),
  }

  onProgress({ status: 'COMPLETED', detail: 'IQM returned exactly 320 hardware measurements. The first 256 are local key material; the separate final 64 are displayed. The raw key is never rendered.' })
  return {
    keyBytes,
    measurementBits,
    source,
    fingerprint: await fingerprintFor(keyBytes),
  }
}

const REVIEW_DEMO_PATTERN = '01101001110010110101000111001010'

/**
 * Deterministic presentation fixture. This branch is called only when the
 * explicit review-demo environment flag is enabled; it makes no API/provider
 * request and never marks its bits as hardware-returned.
 */
export async function requestReviewDemoKey(
  onProgress: (progress: JobProgress) => void,
): Promise<KeyMaterial> {
  const pause = (ms: number) => new Promise<void>((resolve) => globalThis.setTimeout(resolve, ms))
  const demoStep = async (status: string, detail: string, ms: number) => {
    onProgress({ status, detail })
    await pause(ms)
  }

  await demoStep('DEMO_CONNECTING', 'REVIEW DEMO MODE · presenting the intended flow; no live QPU is contacted.', 380)
  await demoStep('DEMO_SUBMITTING', 'HARDWARE FLOW DEMONSTRATION · no circuit is submitted to IQM.', 420)
  await demoStep('DEMO_WAITING', 'PRESENTING THE QPU WAIT PHASE · no real provider queue is queried.', 560)
  await demoStep('DEMO_RUNNING', 'SIMULATING QPU RESPONSE · deterministic review fixture only.', 760)

  const bits = REVIEW_DEMO_PATTERN.repeat(10)
  if (bits.length !== REQUEST_SHOTS || !/^[01]{320}$/.test(bits)) {
    throw new Error('The review demo fixture was invalid. No demo key was created.')
  }
  await demoStep('DEMO_MEASUREMENTS', 'DEMO MEASUREMENTS RECEIVED · 320 deterministic bits, not IQM data.', 260)
  await demoStep('DEMO_PROCESSING', 'PROCESSING 320 DEMO BITS · first 256 for the demo key, final 64 for display.', 220)

  const keyBytes = bitsToBytes(bits.slice(0, KEY_BITS))
  const measurementBits = bits.slice(KEY_BITS, REQUEST_SHOTS)
  const source: KeySource = {
    kind: 'review_demo',
    label: 'REVIEW DEMO · NO LIVE QPU',
    generatedAt: new Date().toISOString(),
  }
  const fingerprint = await fingerprintFor(keyBytes)
  onProgress({ status: 'DEMO_KEY_READY', detail: 'DEMO KEY MATERIAL READY · fingerprint created; raw key is never shown.' })
  return { keyBytes, measurementBits, source, fingerprint }
}

/**
 * An explicit, visibly classical option for local demos. This never runs
 * automatically and never changes the UI's source label to quantum.
 */
export async function generateClassicalKey(): Promise<KeyMaterial> {
  if (!globalThis.crypto?.getRandomValues || !globalThis.crypto?.subtle) {
    throw new Error('A secure browser context is required for the system CSPRNG.')
  }
  const random = new Uint8Array(40)
  globalThis.crypto.getRandomValues(random)
  const keyBytes = random.slice(0, 32)
  const measurementBits = bytesToBits(random.slice(32))
  random.fill(0)
  const source: KeySource = {
    kind: 'classical_csprng',
    label: 'Browser CSPRNG · classical',
    generatedAt: new Date().toISOString(),
  }
  return { keyBytes, measurementBits, source, fingerprint: await fingerprintFor(keyBytes) }
}

function bitsToBytes(bits: string): Uint8Array {
  if (bits.length !== KEY_BITS || !/^[01]+$/.test(bits)) throw new Error('Invalid key bit sequence.')
  const bytes = new Uint8Array(bits.length / 8)
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(bits.slice(i * 8, i * 8 + 8), 2)
  }
  return bytes
}

function bytesToBits(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(2).padStart(8, '0')).join('')
}

function providerLabel(provider: string): string {
  const normalized = provider.toLowerCase()
  if (normalized.includes('iqm')) return 'IQM Quantum Hardware'
  if (normalized.includes('ibm')) return 'IBM Quantum Hardware'
  return `${provider.replace(/_/g, ' ')} · quantum hardware`
}

function describeStatus(status: string): string {
  switch (status) {
    case 'CREATED': return 'The backend created a job record; provider submission has not started yet.'
    case 'VALIDATING': return 'The backend is validating the fixed quantum circuit and IQM configuration.'
    case 'SUBMITTING': return 'The backend is submitting the circuit to IQM.'
    case 'SUBMITTED': return 'IQM accepted the job.'
    case 'QUEUED': return 'The job is queued at IQM, waiting for a quantum processor.'
    case 'RUNNING': return 'The circuit is executing on the IQM quantum processor.'
    case 'FETCHING_RESULT': return 'The completed provider result is being retrieved from the backend.'
    default: return 'Waiting for the IQM provider-returned measurements.'
  }
}
