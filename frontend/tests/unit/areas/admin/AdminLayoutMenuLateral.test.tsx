import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminLayout } from '../../../../src/areas/admin/AdminLayout'
import { fijarAccessToken, obtenerAccessToken } from '../../../../src/lib/auth/tokenStore'
import type { RolDePrueba } from '../../utils/permisosDePrueba'
import { queryClientConYo } from '../../utils/permisosDePrueba'

/**
 * Menú lateral de `/admin`: oculto en todos los tamaños de pantalla, se abre con el botón ☰ de la
 * barra superior como panel superpuesto y se cierra al elegir una sección, al tocar el fondo o con
 * Escape. En el DOM el panel siempre existe (el CSS lo oculta), por eso se verifica con
 * `aria-expanded` y con el fondo oscurecido, que solo existe con el panel abierto.
 */
function montar(rol: RolDePrueba = 'GES', rutaInicial = '/admin/catalogo') {
  const queryClient = queryClientConYo(rol)
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rutaInicial]}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="catalogo" element={<p>Pantalla de catálogo</p>} />
            <Route path="proveedores" element={<p>Pantalla de proveedores</p>} />
          </Route>
          <Route path="/admin/login" element={<p>Pantalla de login</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

const botonMenu = () => screen.getByRole('button', { name: 'Menú' })
const fondo = () => screen.queryByTestId('fondo-del-menu')

describe('AdminLayout: menú lateral desplegable', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('arranca cerrado: el botón ☰ tiene aria-expanded=false y no hay fondo oscurecido', () => {
    montar()

    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
    expect(fondo()).not.toBeInTheDocument()
  })

  it('el botón ☰ abre el panel y vuelve a cerrarlo', async () => {
    const usuario = userEvent.setup()
    montar()

    await usuario.click(botonMenu())
    expect(botonMenu()).toHaveAttribute('aria-expanded', 'true')
    expect(fondo()).toBeInTheDocument()

    await usuario.click(botonMenu())
    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
  })

  it('se cierra al elegir una sección y navega a ella', async () => {
    const usuario = userEvent.setup()
    montar()
    await usuario.click(botonMenu())

    await usuario.click(screen.getByRole('link', { name: 'Proveedores' }))

    expect(await screen.findByText('Pantalla de proveedores')).toBeInTheDocument()
    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
  })

  it('se cierra al tocar el fondo oscurecido', async () => {
    const usuario = userEvent.setup()
    montar()
    await usuario.click(botonMenu())

    await usuario.click(fondo() as HTMLElement)

    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
    expect(fondo()).not.toBeInTheDocument()
  })

  it('se cierra con Escape', async () => {
    const usuario = userEvent.setup()
    montar()
    await usuario.click(botonMenu())

    await usuario.keyboard('{Escape}')

    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
  })

  it('Escape con el panel cerrado no hace nada', async () => {
    const usuario = userEvent.setup()
    montar()

    await usuario.keyboard('{Escape}')

    expect(botonMenu()).toHaveAttribute('aria-expanded', 'false')
  })

  it('la identificación va en la barra superior y no dentro del menú lateral', () => {
    montar('SUP')
    const menu = document.getElementById('menu-lateral') as HTMLElement

    const enBarra = within(screen.getByRole('banner')).getByText(/ · .* · /)
    expect(enBarra).toBeInTheDocument()
    expect(enBarra).toHaveClass('truncate')
    expect(within(menu).queryByText(/ · .* · /)).not.toBeInTheDocument()
  })

  it('"Cerrar sesión" usa el fondo sólido de peligro', () => {
    montar('SUP')

    const boton = screen.getByRole('button', { name: 'Cerrar sesión' })
    expect(boton).toHaveClass('bg-danger', 'text-danger-foreground')
  })

  it('los enlaces del menú llevan letra grande, peso medio y animación con motion-reduce', () => {
    montar('SUP')

    const enlace = screen.getByRole('link', { name: 'Ayuda' })
    expect(enlace).toHaveClass('text-lg', 'font-medium', 'transition-[color,background-color,transform]', 'duration-150', 'motion-reduce:transition-none')
  })

  it('agrupa abajo "Mi cuenta", Ayuda y Cerrar sesión', () => {
    montar('SUP')

    expect(screen.getByRole('navigation', { name: 'Mi cuenta' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mi contraseña' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ayuda' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument()
  })
})

describe('AdminLayout: Cerrar sesión', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    fijarAccessToken('token-vigente')
  })

  it('llama a /auth/logout, vacía la caché y lleva a /admin/login', async () => {
    const usuario = userEvent.setup()
    apiFetchMock.mockResolvedValue({ ok: true, status: 204 })
    const queryClient = montar()

    await usuario.click(screen.getByRole('button', { name: 'Cerrar sesión' }))

    expect(await screen.findByText('Pantalla de login')).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledWith('/auth/logout', { method: 'POST' })
    expect(obtenerAccessToken()).toBeNull()
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
  })

  it('si falla la red muestra el error, no cierra y deja volver a intentar', async () => {
    const usuario = userEvent.setup()
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    montar()

    await usuario.click(screen.getByRole('button', { name: 'Cerrar sesión' }))

    expect(await screen.findByText(/no se pudo cerrar la sesión/i)).toBeInTheDocument()
    expect(screen.queryByText('Pantalla de login')).not.toBeInTheDocument()
    expect(obtenerAccessToken()).toBe('token-vigente')
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeEnabled()
  })

  it('no se dispara dos veces: mientras cierra el botón queda deshabilitado', async () => {
    const usuario = userEvent.setup()
    apiFetchMock.mockReturnValue(new Promise(() => {}))
    montar()

    await usuario.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await usuario.click(screen.getByRole('button', { name: /cerrando/i }))

    expect(apiFetchMock.mock.calls.filter(([ruta]) => ruta === '/auth/logout')).toHaveLength(1)
  })
})
