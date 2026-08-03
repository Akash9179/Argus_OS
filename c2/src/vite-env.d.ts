/// <reference types="vite/client" />

/**
 * Build-time configuration. Only addresses live here: no keys, and nothing
 * that names a model or a provider, because the gateway law keeps those
 * inside the gateway and a bundled frontend is the last place a secret
 * should be.
 */
interface ImportMetaEnv {
  /** Where the voice service is. Defaults to the local one. */
  readonly VITE_VOICE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
