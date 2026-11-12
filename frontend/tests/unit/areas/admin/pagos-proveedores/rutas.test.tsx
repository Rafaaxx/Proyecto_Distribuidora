import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import PagosArea from '../../../../../src/areas/admin/pagos-proveedores/PagosArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { PAGO_ID, montarApi } from './pagosDePrueba'

function renderEn(ruta: string, rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/pagos-proveedores/*" element={<PagosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('rutas de pagos a proveedores en /admin (change 12)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/pagos-proveedores', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      {
        metodo: 'GET',
        ruta: `/pagos-proveedores/${PAGO_ID}`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/pagos-proveedores', /todav[ií]a no hay pagos/i],
    ['/admin/pagos-proveedores/nuevo', /confirmar pago/i],
    [`/admin/pagos-proveedores/${PAGO_ID}`, /no se encontr[oó] el pago/i],
  ])('%s se resuelve a su pantalla', async (ruta, texto) => {
    renderEn(ruta)

    expect(await screen.findByText(texto)).toBeInTheDocument()
  })

  it('con solo ANULAR_PAGO_PROVEEDOR ve el listado sin "Nuevo pago"', async () => {
    renderEn('/admin/pagos-proveedores', 'GES', ['ANULAR_PAGO_PROVEEDOR'])

    expect(await screen.findByText(/todav[ií]a no hay pagos/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /nuevo pago/i })).not.toBeInTheDocument()
  })

  it('con REGISTRAR_PAGO_PROVEEDOR el listado ofrece "Nuevo pago"', async () => {
    renderEn('/admin/pagos-proveedores', 'GES', ['REGISTRAR_PAGO_PROVEEDOR'])

    expect(await screen.findByRole('link', { name: /nuevo pago/i })).toHaveAttribute('href', '/admin/pagos-proveedores/nuevo')
  })

  it('con solo ANULAR_PAGO_PROVEEDOR, /nuevo muestra la falta de permiso', async () => {
    renderEn('/admin/pagos-proveedores/nuevo', 'GES', ['ANULAR_PAGO_PROVEEDOR'])

    expect(await screen.findByText(/no ten[eé]s permiso para registrar pagos/i)).toBeInTheDocument()
  })

  it('sin permisos de pago, el listado muestra la falta de permiso y no pide nada', async () => {
    renderEn('/admin/pagos-proveedores', 'VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver los pagos a proveedores/i)).toBeInTheDocument()
    expect(apiFetchMock.mock.calls.filter(([ruta]) => String(ruta).startsWith('/pagos-proveedores'))).toHaveLength(0)
  })

  it('sin permisos de pago, el detalle muestra la falta de permiso', async () => {
    renderEn(`/admin/pagos-proveedores/${PAGO_ID}`, 'VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver los pagos a proveedores/i)).toBeInTheDocument()
  })
})

describe('entrada de menú "Pagos a proveedores" por rol', () => {
  const ve = (rol: RolDePrueba) =>
    seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Pagos a proveedores')

  it('está declarada y la ven Administrador y Administración, no Supervisor, Vendedor ni Consulta', () => {
    expect(SECCIONES.some((s) => s.ruta === '/admin/pagos-proveedores')).toBe(true)
    expect((['ADM', 'GES', 'SUP', 'VEN', 'CON'] as const).map(ve)).toEqual([true, true, false, false, false])
  })

  it('un usuario con solo ANULAR_PAGO_PROVEEDOR también la ve, y uno con solo REGISTRAR_PAGO_PROVEEDOR', () => {
    const seccionesCon = (permiso: string) =>
      seccionesPermitidas((p) => p === permiso).map((s) => s.etiqueta)

    expect(seccionesCon('ANULAR_PAGO_PROVEEDOR')).toContain('Pagos a proveedores')
    expect(seccionesCon('REGISTRAR_PAGO_PROVEEDOR')).toContain('Pagos a proveedores')
  })

  it('queda a continuación de Compras', () => {
    const etiquetas = SECCIONES.map((s) => s.etiqueta)

    expect(etiquetas.indexOf('Pagos a proveedores')).toBe(etiquetas.indexOf('Compras') + 1)
  })
})
