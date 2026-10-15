import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { yoDePrueba, type RolDePrueba } from '../../utils/permisosDePrueba'

/**
 * Menú y rutas de la ayuda en `/admin` (change 16b, tarea 3.2; spec `ayuda-contextual`,
 * escenario "Usuario sin permisos de descuentos"; ADR-051, D6 = A: la ayuda no depende de
 * permisos). Monta el árbol real de `AdminScreen`; `/yo` responde un rol sin
 * `GESTIONAR_DESCUENTOS`.
 */
function servirYo(rol: RolDePrueba) {
  apiFetchMock.mockImplementation(async (ruta: string) => {
    if (ruta.includes('/yo')) {
      return { ok: true, status: 200, json: async () => yoDePrueba(rol) }
    }
    throw new Error(`Petición inesperada: ${ruta}`)
  })
}

/**
 * `AdminScreen` tiene un `QueryClient` de módulo con `staleTime: Infinity` en `['yo']`: se
 * reimporta por prueba (`vi.resetModules()`) para que el rol de un caso no se filtre al siguiente.
 */
async function montar(ruta: string) {
  const { AdminScreen } = await import('../../../../src/areas/admin/AdminScreen')
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/admin/*" element={<AdminScreen />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetModules()
  apiFetchMock.mockReset()
})

describe('Ayuda en el menú y las rutas de /admin', () => {
  it('un usuario sin GESTIONAR_DESCUENTOS ve "Ayuda" al final del menú y no ve "Descuentos"', async () => {
    servirYo('CON')
    await montar('/admin/ayuda')

    const menu = await screen.findByRole('navigation', { name: /navegación de administración/i })
    await within(menu).findByRole('link', { name: 'Ayuda' })
    const enlaces = within(menu).getAllByRole('link')
    expect(enlaces[enlaces.length - 1]).toHaveTextContent('Ayuda')
    expect(within(menu).queryByRole('link', { name: 'Descuentos' })).not.toBeInTheDocument()
  })

  it('entra a los tres temas desde el índice y no pide nada más que /yo', async () => {
    servirYo('CON')
    const usuario = userEvent.setup()
    await montar('/admin/ayuda')

    for (const [enlace, titulo] of [
      ['Cómo se aplican los descuentos', 'Cómo se aplican los descuentos'],
      ['Cómo funcionan los topes', 'Cómo funcionan los topes'],
      ['Cómo se calcula el precio de una lista', 'Cómo se calcula el precio de una lista'],
    ]) {
      await usuario.click(await screen.findByRole('link', { name: enlace }))
      expect(await screen.findByRole('heading', { level: 1, name: titulo })).toBeInTheDocument()
      await usuario.click(screen.getByRole('link', { name: /volver a ayuda/i }))
    }

    const rutasPedidas = apiFetchMock.mock.calls.map(([ruta]) => String(ruta))
    expect(rutasPedidas.every((ruta) => ruta.includes('/yo'))).toBe(true)
  })

  it('un tema inexistente muestra el aviso dentro de /admin', async () => {
    servirYo('CON')
    await montar('/admin/ayuda/no-existe')

    expect(await screen.findByText('No encontramos ese tema de ayuda')).toBeInTheDocument()
  })

  it('el resto del menú no cambia: Administración sigue viendo Catálogo y Proveedores', async () => {
    servirYo('GES')
    await montar('/admin/ayuda')

    const menu = await screen.findByRole('navigation', { name: /navegación de administración/i })
    expect(await within(menu).findByRole('link', { name: 'Catálogo' })).toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'Ayuda' })).toBeInTheDocument()
  })
})
