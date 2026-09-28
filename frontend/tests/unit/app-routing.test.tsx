import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

/**
 * `/admin` consulta `GET /api/v1/yo` para armar el menú (tarea 7.3, B1) y
 * falla cerrada: sin esa respuesta el menú queda vacío, así que las pruebas
 * de ruteo que buscan enlaces del menú sembrarían un caso imposible. Se
 * intercepta **solo** `/yo` con el cuerpo de un Administrador de `01` §19
 * (que tiene los tres permisos de las secciones) y todo lo demás sigue
 * pasando por el `apiFetch` real, igual que en la línea base: estas pruebas
 * verifican ruteo, no permisos. La visibilidad por permiso se prueba en
 * `areas/admin/AdminLayout.test.tsx`.
 */
vi.mock('../../src/lib/api/httpClient', async () => {
  const real = await vi.importActual<typeof import('../../src/lib/api/httpClient')>('../../src/lib/api/httpClient')
  const { yoDePrueba } = await import('./utils/permisosDePrueba')
  return {
    apiFetch: (ruta: string, init?: RequestInit) => {
      if (ruta === '/yo') {
        return Promise.resolve({ ok: true, status: 200, json: async () => yoDePrueba('ADM') })
      }
      return real.apiFetch(ruta, init)
    },
  }
})

import { AppRoutes } from '../../src/app/AppRoutes'

describe('ruteo de áreas (docs/02 §13.1: /ruta y /admin cargadas de forma diferida)', () => {
  it('muestra la pantalla de /ruta al navegar a /ruta', async () => {
    render(
      <MemoryRouter initialEntries={['/ruta']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/área de ruta/i)).toBeInTheDocument()
  })

  it('redirige /admin al inicio de sesión (change 03, tarea 13.4)', async () => {
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /iniciar sesión/i })).toBeInTheDocument()
  })

  it('muestra la pantalla de dispositivos al navegar a /admin/dispositivos', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/dispositivos']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /dispositivos/i })).toBeInTheDocument()
  })

  it('carga en diferido el área de catálogo al navegar a /admin/catalogo (tarea 10.1)', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/catalogo']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    // El layout de `/admin` (con su navegación) solo se monta si la ruta
    // `catalogo/*` resolvió: si el chunk en diferido no cargara, no habría
    // nada más que el `fallback={null}` del `Suspense`.
    expect(await screen.findByRole('link', { name: /catálogo/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /dispositivos/i })).toBeInTheDocument()
  })

  /**
   * Tarea 7.6 (**B3**, `design.md` D5-A): `/admin/inicio` es la ruta índice
   * dentro del layout, adonde lleva el login, y desde ahí se salta a la
   * primera sección que el usuario puede usar. Con un Administrador (Catálogo
   * y Proveedores, sin Dispositivos -- `01` §19) esa primera sección es
   * Catálogo. Esta prueba verifica el ruteo real de `AdminScreen`, no el
   * criterio de elección (que está en `AdminLayout.test.tsx`).
   */
  it('navegar a /admin/inicio lleva a la primera sección permitida, sin quedarse en el índice', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/inicio']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    // Catálogo es la primera sección del menú para este usuario, así que
    // `/admin/inicio` no debe quedar en la pantalla "Cargando…" del índice.
    expect(await screen.findByRole('heading', { name: /productos/i })).toBeInTheDocument()
  })

  it('redirige la raíz a /ruta', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/área de ruta/i)).toBeInTheDocument()
  })
})

describe('navegación de /admin con rutas absolutas (tarea 10.8, bug reportado en la verificación manual 13.5)', () => {
  it('el enlace "Catálogo" navega a /admin/catalogo estando en /admin/dispositivos, no a /admin/dispositivos/catalogo', async () => {
    const usuario = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/dispositivos']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await screen.findByRole('heading', { name: /dispositivos/i })
    await usuario.click(await screen.findByRole('link', { name: /^catálogo$/i }))

    // Si el enlace fuera relativo, esto navegaría a
    // `/admin/dispositivos/catalogo` (sin ruta que lo resuelva) y no
    // aparecería nada de la pantalla de productos.
    expect(await screen.findByRole('heading', { name: /productos/i })).toBeInTheDocument()
  })

  it('el enlace "Dispositivos" navega a /admin/dispositivos estando en /admin/catalogo/productos/<id>, no se anida bajo esa ruta', async () => {
    const usuario = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/catalogo/productos/11111111-1111-4111-8111-111111111111']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await usuario.click(await screen.findByRole('link', { name: /^dispositivos$/i }))

    expect(await screen.findByRole('heading', { name: /dispositivos/i })).toBeInTheDocument()
  })

  it('"Nuevo producto" navega a /admin/catalogo/productos/nuevo desde el listado', async () => {
    const usuario = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/catalogo/productos']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await usuario.click(await screen.findByRole('link', { name: /nuevo producto/i }))

    expect(await screen.findByRole('heading', { name: /nuevo producto/i })).toBeInTheDocument()
  })

  it('"Categorías y marcas" navega a /admin/catalogo/categorias-y-marcas desde el listado de productos', async () => {
    const usuario = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/catalogo/productos']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    await usuario.click(await screen.findByRole('link', { name: /categorías y marcas/i }))

    expect(await screen.findByRole('heading', { name: /^categorías y marcas$/i })).toBeInTheDocument()
  })
})
