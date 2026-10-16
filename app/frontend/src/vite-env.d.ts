/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_QUANTUM_REVIEW_DEMO?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
