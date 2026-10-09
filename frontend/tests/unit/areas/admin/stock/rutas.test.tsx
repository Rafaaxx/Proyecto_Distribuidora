import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import StockArea from '../../../../../src/areas/admin/stock/StockArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { enrutar } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ID = '11111111-1111-4111-8111-111111111111'
const PRODUCTO = '22222222-2222-4222-8222-222222222222'

function renderEn(ruta: string, rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/stock/*" element={<StockArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Change 09, tarea 8.2 a 8.4: todas las pantallas de stock cuelgan de una sola
 * sección del menú, `/admin/stock` (D15). */
describe('rutas de stock en /admin (change 09)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: { items: [{ id: ID, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: '2026-01-01T00:00:00Z' }], cursor_siguiente: null } }) },
      { ruta: `/stock/ubicaciones/${ID}/saldos`, responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      { ruta: '/stock/kardex', responder: () => ({ status: 200, cuerpo: { saldo_anterior: 0, saldo_actual: 0, zona_horaria: 'UTC', producto_codigo: 'C', producto_nombre: 'Vino A', unidades_referencia: null, nombre_referencia: null, items: [], cursor_siguiente: null } }) },
      { ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      { ruta: '/stock/transferencias', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      { ruta: '/stock/ajustes', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      { ruta: '/configuracion/motivos', responder: () => ({ status: 200, cuerpo: { items: [] } }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/stock', 'Nueva ubicación'],
    ['/admin/stock/ubicaciones/nueva', 'Guardar'],
    [`/admin/stock/ubicaciones/${ID}`, 'Guardar'],
    [`/admin/stock/ubicaciones/${ID}/stock`, 'No hay stock en esta ubicación.'],
    [`/admin/stock/ubicaciones/${ID}/kardex/${PRODUCTO}`, 'No hay movimientos en este período.'],
    [`/admin/stock/ubicaciones/${ID}/stock-inicial`, 'Registrar stock inicial'],
    ['/admin/stock/transferencias', 'No hay transferencias para mostrar.'],
    ['/admin/stock/transferencias/nueva', 'Registrar transferencia'],
    ['/admin/stock/ajustes', 'No hay ajustes para mostrar.'],
    ['/admin/stock/ajustes/nueva', 'Registrar ajuste'],
  ])('%s se resuelve a su pantalla', async (ruta, texto) => {
    renderEn(ruta)

    expect(await screen.findByText(texto)).toBeInTheDocument()
  })
})

describe('sección "Stock" del menú (D3, D15)', () => {
  it('está declarada con TRANSFERIR_STOCK y se ofrece a Administrador, Administración, Supervisor y Vendedor, no a Consulta', () => {
    const seccion = SECCIONES.find((s) => s.ruta === '/admin/stock')
    expect(seccion).toEqual({ ruta: '/admin/stock', etiqueta: 'Stock', permiso: 'TRANSFERIR_STOCK' })

    const ve = (rol: RolDePrueba) =>
      seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Stock')
    expect(['ADM', 'GES', 'SUP', 'VEN'].map((r) => ve(r as RolDePrueba))).toEqual([true, true, true, true])
    expect(ve('CON')).toBe(false)
  })
})
