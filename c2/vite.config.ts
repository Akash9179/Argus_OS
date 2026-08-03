import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The world model server is reached through a dev proxy so that the
// application uses same-origin paths in development and in production
// alike. C2 never learns a hostname.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      '/v1': { target: 'http://localhost:8100', changeOrigin: true, ws: true },
      '/health': { target: 'http://localhost:8100', changeOrigin: true },
    },
  },
})
