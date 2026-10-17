import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import CobranzasArea from '../../../../../src/areas/admin/cobranzas/CobranzasArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { COBRANZA_ID, montarApi } from './cobranzasDePrueba'

function renderEn(ruta: string, rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/cobranzas/*" element={<CobranzasArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('rutas de cobranzas en /admin (change 17)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      {
        metodo: 'GET',
        ruta: `/cobranzas/${COBRANZA_ID}`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/cobranzas', /todav[ií]a no hay cobranzas/i],
    ['/admin/cobranzas/nuevo', /confirmar cobranza/i],
    [`/admin/cobranzas/${COBRANZA_ID}`, /no se encontr[oó] la cobranza/i],
  ])('%s se resuelve a su pantalla (nuevo se declara antes que :cobranzaId)', async (ruta, texto) => {
    renderEn(ruta)

    expect(await screen.findByText(texto)).toBeInTheDocument()
  })

  it('con solo ANULAR_COBRANZA, /nuevo muestra la falta de permiso', async () => {
    renderEn('/admin/cobranzas/nuevo', 'GES', ['ANULAR_COBRANZA'])

    expect(await screen.findByText(/no ten[eé]s permiso para registrar cobranzas/i)).toBeInTheDocument()
  })

  it('sin permisos de cobranza, el detalle muestra la falta de permiso', async () => {
    renderEn(`/admin/cobranzas/${COBRANZA_ID}`, 'CON')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las cobranzas/i)).toBeInTheDocument()
  })
})

describe('entrada de menú "Cobranzas" por permiso (D14, D19)', () => {
  const ve = (rol: RolDePrueba) =>
    seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Cobranzas')
  const seccionesCon = (permiso: string) => seccionesPermitidas((p) => p === permiso).map((s) => s.etiqueta)

  it('está declarada y la ve quien tiene alguno de los dos permisos de cobranza', () => {
    expect(SECCIONES.some((s) => s.ruta === '/admin/cobranzas')).toBe(true)
    for (const rol of ['ADM', 'GES', 'SUP', 'VEN', 'CON'] as const) {
      const tiene = PERMISOS_POR_ROL[rol].some((p) => p === 'REGISTRAR_COBRANZA' || p === 'ANULAR_COBRANZA')
      expect([rol, ve(rol)]).toEqual([rol, tiene])
    }
  })

  it('el Vendedor la ve y Consulta no (escenarios de la spec)', () => {
    expect(ve('VEN')).toBe(true)
    expect(ve('CON')).toBe(false)
  })

  it('con solo REGISTRAR_COBRANZA o solo ANULAR_COBRANZA también la ve', () => {
    expect(seccionesCon('REGISTRAR_COBRANZA')).toContain('Cobranzas')
    expect(seccionesCon('ANULAR_COBRANZA')).toContain('Cobranzas')
    expect(seccionesCon('GESTIONAR_CLIENTES')).not.toContain('Cobranzas')
  })

  it('queda a continuación de Clientes', () => {
    const etiquetas = SECCIONES.map((s) => s.etiqueta)

    expect(etiquetas.indexOf('Cobranzas')).toBe(etiquetas.indexOf('Clientes') + 1)
  })
})
