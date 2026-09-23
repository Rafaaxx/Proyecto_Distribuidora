import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

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
