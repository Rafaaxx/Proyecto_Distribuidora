/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Change 21, D17 (`design.md`): service worker generado (`generateSW`) sin código propio.
    // Precachea el shell, el área /ruta, la ayuda y pdfmake con sus fuentes; el código de /admin
    // sale a `assets/admin/` (ver `chunkFileNames`) y queda fuera del precache (`02` §13.1). Sin
    // `runtimeCaching`: ninguna respuesta de /api/ se guarda ni se sirve de caché (`02` §13.5).
    // `registerType: 'prompt'`: la versión nueva espera a que el usuario toque "Actualizar".
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      includeAssets: ['apple-touch-icon.png', 'favicon.svg'],
      manifest: {
        name: 'Distribuidora',
        short_name: 'Distribuidora',
        description: 'Venta en ruta de la distribuidora',
        lang: 'es-AR',
        start_url: '/ruta',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        theme_color: '#1d4e9f',
        background_color: '#ffffff',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'],
        globIgnores: ['assets/admin/**'],
        navigateFallback: 'index.html',
        // /admin no se sirve desde el shell precacheado: siempre va a la red (así nunca queda un shell
        // viejo apuntando a fragmentos de administración que ya no existen).
        navigateFallbackDenylist: [/^\/api\//, /^\/admin/],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        // El código de /admin va a una carpeta propia para excluirlo del precache por patrón.
        chunkFileNames: (chunk) =>
          chunk.moduleIds.some((id) => /[\\/]src[\\/]areas[\\/]admin[\\/]/.test(id))
            ? 'assets/admin/[name]-[hash].js'
            : 'assets/[name]-[hash].js',
      },
    },
  },
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
    // El módulo virtual del registro del service worker solo existe dentro del build.
    alias: { 'virtual:pwa-register/react': fileURLToPath(new URL('./tests/unit/utils/pwaRegisterStub.ts', import.meta.url)) },
  },
})
