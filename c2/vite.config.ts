import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// The visual language lives one level up, in design/, shared with the
// cockpit. The dev server is allowed to read that directory and nothing
// else outside its own root (var/ holds tokens).
const appRoot = fileURLToPath(new URL('.', import.meta.url))
const designDir = fileURLToPath(new URL('../design', import.meta.url))

// The world model server is reached through a dev proxy so that the
// application uses same-origin paths in development and in production
// alike. C2 never learns a hostname.
export default defineConfig({
  plugins: [react()],
  server: {
    // testing tunnels: quick-tunnel hostnames rotate, so allow the suffix
    allowedHosts: ['.trycloudflare.com'],
    port: 5180,
    fs: { allow: [appRoot, designDir] },
    proxy: {
      '/v1': { target: 'http://localhost:8100', changeOrigin: true, ws: true },
      '/health': { target: 'http://localhost:8100', changeOrigin: true },
    },
  },
})
