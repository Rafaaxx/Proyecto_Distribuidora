import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { PERMISOS_POR_ROL, yoDePrueba } from '../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PAGINA_VACIA = { items: [], cursor_siguiente: null }
const CATEGORIA_ID = '11111111-1111-4111-8111-111111111111'
const PRODUCTO = {
  id: '33333333-3333-4333-8333-333333333333',
  codigo: 'GAS-001',
  nombre: 'Gaseosa cola',
  categoria_id: CATEGORIA_ID,
  marca_id: null,
  unidad_base: 'unidad',
  alicuota_id: '22222222-2222-4222-8222-222222222222',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}
const PRODUCTO_DETALLE = {
  ...PRODUCTO,
  proveedor_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  proveedor_nombre: 'Bodega Andina',
  presentaciones: [],
}

/**
 * Spec `identidad/permisos-efectivos`, escenarios "Tras renovar el token, la
 * interfaz refleja un permiso quitado" y "Navegar no renueva el token"
 * (tarea 10.1 del grupo 10 del change 06b, ADR-027: "un pedido extra por
 * sesión y por renovación").
 *
 * Qué faltaba y este archivo cierra: hasta acá las dos piezas --
 * `AdminScreen.test.tsx` ("al fijarse un token, invalida ['yo']") y
 * `AdminLayout.test.tsx` ("Administración ve Catálogo y Proveedores") --
 * vivían separadas, y ninguna afirmaba el efecto que el escenario pide: que
 * la entrada "Proveedores" *desaparezca del menú* cuando la renovación
 * devuelve permisos distintos, sin recargar la página. Aquí se monta el
 * árbol real completo (`AdminScreen`: `QueryClient` interno + suscripción a
 * `tokenStore` + `AdminLayout` + áreas reales diferidas) y se maneja la
 * renovación con `fijarAccessToken`, que es lo que llama `httpClient` tras
 * un `POST /auth/refresh` exitoso.
 *
 * `vi.resetModules()` por prueba es obligatorio: el `QueryClient` de
 * `AdminScreen.tsx` es un singleton de módulo y `usePermisos()` usa
 * `staleTime: Infinity` (ADR-027), así que sin reiniciar el registro de
 * módulos el `['yo']` del caso anterior seguiría cacheado y este archivo no
 * mediría nada.
 *
 * Las formas de los datos de catálogo y proveedores NO se tipan contra el
 * OpenAPI acá a propósito: cada pantalla ya las fija contra el contrato real
 * en su propio archivo (`ProductosListScreen.test.tsx`,
 * `ProveedorFormScreen.test.tsx`...). Lo que este archivo tiene que detectar
 * es el comportamiento de `/yo`, no una forma de datos.
 */
describe('AdminScreen: reflejo de permisos al renovar el token (tarea 10.1)', () => {
  beforeEach(() => {
    vi.resetModules()
    apiFetchMock.mockReset()
  })

  /** Enruta solo lo que el árbol montado pide. `yoActual` es una función
   * para poder cambiar la respuesta de `/yo` a mitad de la prueba (que es
   * exactamente lo que hace una renovación con otro rol). */
  function enrutar(yoActual: () => unknown) {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta === '/yo') return Promise.resolve(respuesta(200, yoActual()))
      if (ruta === `/catalogo/productos/${PRODUCTO.id}`) {
        return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
      }
      if (String(ruta).startsWith('/catalogo/categorias')) {
        return Promise.resolve(respuesta(200, PAGINA_VACIA))
      }
      if (String(ruta).startsWith('/catalogo/marcas')) {
        return Promise.resolve(respuesta(200, PAGINA_VACIA))
      }
      if (String(ruta).startsWith('/configuracion/alicuotas')) {
        return Promise.resolve(respuesta(200, PAGINA_VACIA))
      }
      if (String(ruta).startsWith('/proveedores')) {
        return Promise.resolve(respuesta(200, PAGINA_VACIA))
      }
      if (String(ruta).startsWith('/catalogo/productos')) {
        return Promise.resolve(respuesta(200, { items: [PRODUCTO], cursor_siguiente: null }))
      }
      throw new Error(`ruta inesperada: ${ruta}`)
    })
  }

  function llamadasAYo(): unknown[][] {
    return apiFetchMock.mock.calls.filter(([ruta]) => ruta === '/yo')
  }

  /**
   * Monta `AdminScreen` con la misma composición real que `AppRoutes`
   * (`/admin/*`): las rutas de `AdminScreen` son relativas al router, así
   * que sin este envoltorio `/admin/catalogo/productos` no resolvería
   * `catalogo/*` y el árbol quedaría vacío -- el mismo montaje que usa
   * `app-routing.test.tsx`.
   */
  function montarAdmin() {
    return import('../../../../src/areas/admin/AdminScreen').then(({ AdminScreen }) =>
      render(
        <MemoryRouter initialEntries={['/admin/catalogo/productos']}>
          <Routes>
            <Route path="/admin/*" element={<AdminScreen />} />
          </Routes>
        </MemoryRouter>,
      ),
    )
  }

  it('tras renovar el token, "Proveedores" desaparece del menú sin recargar la página (escenario "Tras renovar el token, la interfaz refleja un permiso quitado")', async () => {
    let yo = yoDePrueba('GES')
    enrutar(() => yo)

    await montarAdmin()
    const { fijarAccessToken } = await import('../../../../src/lib/auth/tokenStore')

    // GES tiene `GESTIONAR_PROVEEDORES` (01-dominio.md §19): el menú abre
    // con Catálogo y Proveedores, y `/yo` se consultó una sola vez.
    expect(await screen.findByRole('link', { name: 'Proveedores' })).toBeInTheDocument()
    expect(llamadasAYo()).toHaveLength(1)

    // El servidor responde a la renovación con el mismo usuario pero sin
    // `GESTIONAR_PROVEEDORES` (permiso editado entre una sesión y la otra).
    yo = yoDePrueba('GES', {
      permisos: PERMISOS_POR_ROL.GES.filter((codigo) => codigo !== 'GESTIONAR_PROVEEDORES'),
    })
    // La renovación de verdad: `httpClient` llama `fijarAccessToken` después
    // de un `POST /auth/refresh` exitoso, y eso dispara la invalidación.
    // Sin esta línea la prueba falla (verificado en el paso RED).
    act(() => fijarAccessToken('access-token-renovado'))

    // La entrada desaparece del menú, sin recargar la página.
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Proveedores' })).not.toBeInTheDocument())

    // Y la consulta de sesión se repitió exactamente una vez más: la
    // renovación invalida `['yo']` (tarea 6.5), no lo re-pregunta cada
    // navegación (ADR-027).
    expect(llamadasAYo()).toHaveLength(2)
  })

  it('navega entre Catálogo, Proveedores y la ficha de un producto sin renovar el token: la consulta de sesión se hizo una sola vez (escenario "Navegar no renueva el token")', async () => {
    enrutar(() => yoDePrueba('GES'))

    const usuarioEvento = userEvent.setup()
    await montarAdmin()

    expect(await screen.findByText('Gaseosa cola')).toBeInTheDocument()
    expect(llamadasAYo()).toHaveLength(1)

    await usuarioEvento.click(screen.getByRole('link', { name: 'Proveedores' }))
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(([ruta]) => String(ruta).startsWith('/proveedores')),
      ).toBe(true),
    )

    await usuarioEvento.click(screen.getByRole('link', { name: 'Catálogo' }))
    expect(await screen.findByText('Gaseosa cola')).toBeInTheDocument()

    await usuarioEvento.click(screen.getByRole('link', { name: 'GAS-001' }))
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(([ruta]) => ruta === `/catalogo/productos/${PRODUCTO.id}`),
      ).toBe(true),
    )

    expect(llamadasAYo()).toHaveLength(1)
  })
})
