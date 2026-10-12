import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { withoutKey } from './src/ui/driveAddress'

// The visual language lives one level up, in design/, shared with the
// cockpit. The dev server is allowed to read that directory and nothing
// else outside its own root (var/ holds tokens).
const appRoot = fileURLToPath(new URL('.', import.meta.url))
const designDir = fileURLToPath(new URL('../design', import.meta.url))

// The world model server is reached through a dev proxy so that the
// application uses same-origin paths in development and in production
// alike. C2 never learns a hostname.
export default defineConfig(({ mode }) => {
  // Vite writes every VITE_ value into the bundle as a literal. A bridge key
  // in VITE_DRIVE_URL would therefore ship to anyone holding the build, so
  // the key is taken out here, before the value reaches the bundle. The
  // cockpit asks the operator for the key itself.
  const configured = loadEnv(mode, appRoot, 'VITE_').VITE_DRIVE_URL
  const define: Record<string, string> = {}
  if (configured !== undefined) {
    const { url, hadKey } = withoutKey(configured)
    if (hadKey) console.warn('ARGUS: VITE_DRIVE_URL carried a bridge key. It was left out of the build.')
    define['import.meta.env.VITE_DRIVE_URL'] = JSON.stringify(url)
  }
  return {
    define,
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
  }
})
