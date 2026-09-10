import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// design/tokens.css is shared with c2/ and lives at the repository root.
const repoRoot = fileURLToPath(new URL('../..', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // testing tunnels: quick-tunnel hostnames rotate, so allow the suffix
    allowedHosts: ['.trycloudflare.com'],
    fs: { allow: [repoRoot] },
  },
})
