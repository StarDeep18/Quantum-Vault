# Quantum Vault

**Your secrets. Locked with randomness from quantum measurement.**

A local-first prototype that uses real quantum hardware to generate encryption keys. It talks to the QRNG backend, pulls 256 bits from a live QPU measurement and uses them as key material for AES-256-GCM encryption. A separate 64-bit window from the same batch is shown as telemetry - those bits are not part of the key.

> Prototype demonstration. Not intended for production credential storage.

---

## Getting started

### 1. Frontend

From the project root:

```bash
npm install
npm run dev
```

Vite serves the app at `http://localhost:5173` and proxies `/api` to `http://127.0.0.1:8000`.

### 2. Backend

In a second terminal:

```bash
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn qlab.main:app --host 0.0.0.0 --port 8000
```

### 3. Hardware credentials

Copy the template and fill in your provider credentials:

```bash
cp app/backend/.env.example app/backend/.env
```

Set either:

- **IQM** — `IQM_SERVER_URL` + `IQM_ACCESS_TOKEN` (preferred)
- **IBM Quantum** — `IBM_QUANTUM_API_KEY`

Credentials stay server-side. Nothing is bundled into the browser app. The backend re-reads the config each time a job is submitted.

The vault pins `IQM_QUANTUM_COMPUTER=sirius` and validates it against live discovery. If the API is unreachable, credentials are missing or no real QPU is operational, the app shows **QUANTUM HARDWARE UNAVAILABLE**. You can explicitly choose **Use system randomness instead** to create a local vault backed by the browser's Web Crypto CSPRNG - clearly labeled **CLASSICAL / SYSTEM CSPRNG** throughout. There is no silent fallback.

---

## Review Demo Mode

`QUANTUM_REVIEW_DEMO` defaults to `false`. To run a walkthrough without real hardware:

```bash
# app/backend/.env
QUANTUM_REVIEW_DEMO=true
```

Restart the API after changing it. The demo uses a fixed 320-bit fixture (first 256 bits → vault key, last 64 bits → telemetry display). No circuit is sent to any provider. All labels read **REVIEW DEMO · NO LIVE QPU**. Demo vaults keep that provenance tag permanently — don't store real secrets in them.

---

## What it does

- **3D vault scene** - procedural Three.js door with hinges, a central wheel and sliding radial bolts. Lock and unlock animate the full mechanism.
- **Key ceremony** - step-by-step display of `|0⟩ → H → measurement` through to AES-GCM encryption.
- **Honest hardware status** - live provider-job polling, progressive reveal of the 64-bit telemetry window.
- **Vault management** - create, unlock, store passwords/API keys/notes, reveal, copy, edit, delete.
- **Encrypted local storage** - IndexedDB (with encrypted `localStorage` fallback). Vault contents and the wrapped key are ciphertext at rest. The master password is never stored.
- **UI** - light/dark themes, responsive layouts, reduced-motion support.

---

## Cryptographic boundaries

| What | How |
|------|-----|
| Encryption | AES-256-GCM |
| Key wrapping | PBKDF2-HMAC-SHA-256, 600k iterations |
| Nonces / salts | `crypto.getRandomValues` (never described as quantum) |
| Hardware key | Imported as non-extractable; wrapped with the password-derived key |
| Password verification | Authenticated decryption — no stored verifier |
| Raw bits | Never written to the backend's plaintext JSONL log |

Keys are best-effort cleared from typed arrays when no longer needed. JavaScript cannot guarantee complete memory zeroization. This is a prototype - do not use it for real credentials.

---

## Project layout

```
app/
├── backend/
│   ├── qlab/          FastAPI QRNG backend (IQM-first, IBM fallback)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── components/    Vault scene, key ceremony, editor, screens
        ├── services/      QRNG client, crypto, IndexedDB, vault logic
        ├── App.tsx
        └── styles.css
```
