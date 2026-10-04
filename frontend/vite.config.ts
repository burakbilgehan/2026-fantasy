import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // GitHub Pages serves the static build under /2026-fantasy/.
  base: process.env.VITE_STATIC === '1' ? '/2026-fantasy/' : '/',
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
