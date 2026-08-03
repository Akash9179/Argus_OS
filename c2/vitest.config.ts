/// <reference types="vitest" />
/**
 * The test harness. It exists because two real behaviour bugs sat in the
 * mode switch until a browser session found them: a no-op click cancelled
 * a running order, and entering Manual cancelled operator orders and
 * called them the station's. Every frontend claim before this rested on
 * someone driving the app by hand.
 */
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
