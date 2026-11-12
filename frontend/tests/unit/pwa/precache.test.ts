// @vitest-environment node
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative, resolve, sep } from 'node:path'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { build } from 'vite'

/**
 * Change 21, tarea 11.2 (spec `sistema/aplicacion-instalable`; `design.md` D17; `02` §13.1, §13.5;
 * VTA-13). Corre el build de producción en una carpeta temporal y revisa el service worker
 * generado: precachea el shell, el área `/ruta`, la ayuda y pdfmake con sus fuentes; no precachea
 * nada de `/admin`; no guarda respuestas de `/api/` ni define cachés de ejecución.
 */
const RAIZ = resolve(__dirname, '../../..')
let salida = ''
let sw = ''
let urls: string[] = []

function leer(ruta: string): string {
  return readFileSync(join(salida, ruta), 'utf-8')
}

function archivos(carpeta: string): string[] {
  return readdirSync(carpeta).flatMap((nombre) => {
    const ruta = join(carpeta, nombre)
    return statSync(ruta).isDirectory() ? archivos(ruta) : [ruta]
  })
}

/** Cadenas que solo existen en el código de las pantallas de `/admin`. */
const MARCAS_DE_ADMIN = ['/admin/stock/jornadas', '/admin/descuentos', '/admin/importacion', '/admin/cobranzas']

beforeAll(async () => {
  salida = mkdtempSync(join(tmpdir(), 'build-pwa-'))
  // Vitest corre con NODE_ENV=test; el plugin PWA usaría el modo de desarrollo (sin minificar).
  vi.stubEnv('NODE_ENV', 'production')
  await build({
    root: RAIZ,
    configFile: join(RAIZ, 'vite.config.ts'),
    mode: 'production',
    logLevel: 'silent',
    build: { outDir: salida, emptyOutDir: true, reportCompressedSize: false },
  })
  sw = leer('sw.js')
  urls = [...sw.matchAll(/url:\s*"([^"]+)"/g)].map((m) => m[1] ?? '')
}, 300_000)

afterAll(() => {
  vi.unstubAllEnvs()
  if (salida) rmSync(salida, { recursive: true, force: true })
})

describe('precache del service worker (tarea 11.2)', () => {
  it('incluye el shell, el área de ruta, la ayuda y pdfmake con sus fuentes', () => {
    expect(urls).toContain('index.html')
    expect(urls.some((u) => /pdfmake-.*\.js$/.test(u))).toBe(true)
    expect(urls.some((u) => /vfs_fonts-.*\.js$/.test(u))).toBe(true)

    const js = urls.filter((u) => u.endsWith('.js')).map((u) => leer(u))
    expect(js.some((c) => c.includes('Hay una versión nueva'))).toBe(true) // área /ruta
    expect(js.some((c) => c.includes('Este navegador no garantiza'))).toBe(true) // textos de ayuda
  })

  it('no incluye ningún fragmento del área /admin', () => {
    const js = urls.filter((u) => u.endsWith('.js'))
    expect(js.filter((u) => u.includes('admin/'))).toEqual([])
    for (const url of js) {
      const contenido = leer(url)
      for (const marca of MARCAS_DE_ADMIN) {
        expect(contenido.includes(marca), `${url} contiene ${marca}`).toBe(false)
      }
    }
  })

  it('el código de /admin existe en el build pero fuera del precache', () => {
    const construidos = archivos(join(salida, 'assets')).map((a) => relative(salida, a).split(sep).join('/'))
    const deAdmin = construidos.filter((a) => a.startsWith('assets/admin/'))
    expect(deAdmin.length).toBeGreaterThan(0)
    expect(urls.filter((u) => u.startsWith('assets/admin/'))).toEqual([])
  })

  it('deniega /api/ (y /admin) en la navegación y no define cachés de ejecución', () => {
    expect(sw).toContain(String.raw`denylist:[/^\/api\//,/^\/admin/]`)
    expect(sw.match(/registerRoute\(/g)?.length).toBe(1)
    expect(sw).toContain('NavigationRoute')
    expect(sw).not.toMatch(/CacheFirst|NetworkFirst|StaleWhileRevalidate|runtimeCaching/)
  })

  it('el manifiesto es instalable: start_url /ruta y display standalone', () => {
    const manifiesto = JSON.parse(leer('manifest.webmanifest')) as Record<string, unknown>
    expect(manifiesto.start_url).toBe('/ruta')
    expect(manifiesto.display).toBe('standalone')
    expect(Array.isArray(manifiesto.icons) && manifiesto.icons.length >= 2).toBe(true)
  })
})
