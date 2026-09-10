import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// The visual language lives one level up, in design/, shared with the
// cockpit. The dev server has to be allowed to read it from there.
const repoRoot = fileURLToPath(new URL('..', import.meta.url))

// The world model server is reached through a dev proxy so that the
// application uses same-origin paths in development and in production
// alike. C2 never learns a hostname.
export default defineConfig({
  plugins: [react()],
  server: {
    // testing tunnels: quick-tunnel hostnames rotate, so allow the suffix
    allowedHosts: ['.trycloudflare.com'],
    port: 5180,
    fs: { allow: [repoRoot] },
    proxy: {
      '/v1': { target: 'http://localhost:8100', changeOrigin: true, ws: true },
      '/health': { target: 'http://localhost:8100', changeOrigin: true },
    },
  },
})
