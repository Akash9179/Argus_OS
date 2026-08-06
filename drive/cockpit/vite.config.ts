import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // testing tunnels: quick-tunnel hostnames rotate, so allow the suffix
    allowedHosts: ['.trycloudflare.com'],
  },
})
