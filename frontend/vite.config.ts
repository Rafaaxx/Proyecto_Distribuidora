/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // `docs/02-arquitectura.md`: frontend y API en el mismo origen, sin CORS
    // abierto. En producción lo resuelve Caddy (proxy de `/api`); en
    // desarrollo (`docker compose up`, sin Caddy) este proxy hace el mismo
    // papel para que el navegador solo vea el origen de Vite.
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/unit/setup.ts'],
    include: ['tests/unit/**/*.test.{ts,tsx}'],
  },
})
