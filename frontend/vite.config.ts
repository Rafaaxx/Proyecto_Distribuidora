/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Con Docker Desktop en Windows, los cambios en el volumen montado no
    // generan eventos del sistema de archivos dentro del contenedor: sin
    // polling, Vite no recarga. Se activa solo desde `docker-compose.yml`
    // para no gastar CPU al correr `npm run dev` en el host.
    watch: {
      usePolling: process.env.VITE_USE_POLLING === 'true',
      interval: 300,
    },
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
