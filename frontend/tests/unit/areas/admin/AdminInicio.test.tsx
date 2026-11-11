import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminInicio } from '../../../../src/areas/admin/AdminInicio'
import { AdminLayout } from '../../../../src/areas/admin/AdminLayout'
import { queryClientConYo, type RolDePrueba } from '../../utils/permisosDePrueba'

function montar(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/inicio']}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="inicio" element={<AdminInicio />} />
            <Route path="catalogo" element={<p>Pantalla de catálogo</p>} />
            <Route path="reportes" element={<p>Pantalla de reportes</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function resumen(campos: Partial<Record<string, unknown>> = {}) {
  return {
    observaciones_por_codigo: {},
    observaciones_pendientes: 0,
    rechazos_pendientes: 0,
    cuarentenas_pendientes: 0,
    total_pendiente: 0,
    ...campos,
  }
}

function responderConResumen(cuerpo: unknown) {
  apiFetchMock.mockImplementation(() => Promise.resolve({ ok: true, status: 200, json: async () => cuerpo }))
}

const llamadasAlResumen = () => apiFetchMock.mock.calls.filter(([ruta]) => ruta === '/observaciones/resumen')

/**
 * Change 25, tarea 15.1 (spec `sync/revision-de-observaciones`, «Administración ve un aviso de lo pendiente»;
 * D5; CRE-09, SEG-06): la tarjeta «Para revisar» del inicio de `/admin`.
 */
describe('AdminInicio: tarjeta «Para revisar» (tarea 15.1, D5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('muestra los avisos y las operaciones rechazadas pendientes, con acceso a cada lista', async () => {
    responderConResumen(
      resumen({ observaciones_pendientes: 5, rechazos_pendientes: 2, cuarentenas_pendientes: 1, total_pendiente: 8 }),
    )
    montar('GES')

    const tarjeta = await screen.findByRole('region', { name: 'Para revisar' })
    expect(await within(tarjeta).findByRole('link', { name: '5 avisos pendientes' })).toHaveAttribute('href', '/admin/revision')
    expect(within(tarjeta).getByRole('link', { name: '3 operaciones rechazadas sin resolver' })).toHaveAttribute(
      'href',
      '/admin/revision/rechazadas',
    )
    expect(within(tarjeta).queryByText(/excesos? de crédito/)).not.toBeInTheDocument()
  })

  it('los excesos de crédito detectados al sincronizar van aparte, con la bandeja filtrada por ese código (CRE-09)', async () => {
    responderConResumen(
      resumen({
        observaciones_por_codigo: { EXCESO_CREDITO_DETECTADO_SYNC: 2, STOCK_NEGATIVO: 1 },
        observaciones_pendientes: 3,
        total_pendiente: 3,
      }),
    )
    montar('GES')

    const enlace = await screen.findByRole('link', { name: '2 excesos de crédito detectados al sincronizar' })
    expect(enlace).toHaveAttribute('href', '/admin/revision?codigo=EXCESO_CREDITO_DETECTADO_SYNC')
  })

  it('con un solo exceso lo dice en singular', async () => {
    responderConResumen(
      resumen({
        observaciones_por_codigo: { EXCESO_CREDITO_DETECTADO_SYNC: 1 },
        observaciones_pendientes: 1,
        total_pendiente: 1,
      }),
    )
    montar('GES')

    expect(await screen.findByRole('link', { name: '1 exceso de crédito detectado al sincronizar' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: '1 aviso pendiente' })).toBeInTheDocument()
  })

  it('sin nada pendiente dice «Sin avisos pendientes.» y el menú no muestra contador', async () => {
    responderConResumen(resumen())
    montar('GES')

    expect(await screen.findByText('Sin avisos pendientes.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Revisión' })).toBeInTheDocument()
  })

  it('el contador del menú sube con el total pendiente', async () => {
    responderConResumen(resumen({ observaciones_pendientes: 1, total_pendiente: 1 }))
    montar('GES')

    expect(await screen.findByRole('link', { name: 'Revisión 1' })).toBeInTheDocument()
  })

  it('se actualiza solo cada 60 segundos, sin recargar la página', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    responderConResumen(resumen())
    montar('GES')
    await screen.findByText('Sin avisos pendientes.')
    expect(llamadasAlResumen()).toHaveLength(1)

    responderConResumen(resumen({ observaciones_pendientes: 1, total_pendiente: 1 }))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(await screen.findByRole('link', { name: '1 aviso pendiente' })).toBeInTheDocument()
    expect(llamadasAlResumen().length).toBeGreaterThanOrEqual(2)
  })

  it('al volver a la pestaña vuelve a pedir el resumen', async () => {
    responderConResumen(resumen())
    montar('GES')
    await screen.findByText('Sin avisos pendientes.')
    const antes = llamadasAlResumen().length

    act(() => {
      window.dispatchEvent(new Event('visibilitychange'))
    })

    await waitFor(() => expect(llamadasAlResumen().length).toBeGreaterThan(antes))
  })

  it('si el resumen falla no inventa números', async () => {
    apiFetchMock.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, json: async () => ({ title: 'Error del servidor.' }) }),
    )
    montar('GES')

    expect(await screen.findByRole('region', { name: 'Para revisar' })).toBeInTheDocument()
    await waitFor(() => expect(llamadasAlResumen().length).toBeGreaterThan(0))
    expect(screen.queryByText('Sin avisos pendientes.')).not.toBeInTheDocument()
    expect(screen.queryByText(/avisos? pendientes?/)).not.toBeInTheDocument()
  })

  it('sin REVISAR_OBSERVACIONES no hay tarjeta, no se pide el resumen y el inicio sigue llevando a la primera sección', async () => {
    montar('VEN')

    // El Vendedor no tiene secciones de este arbol de prueba: aterriza en su mensaje, sin tarjeta.
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Para revisar' })).not.toBeInTheDocument())
    expect(llamadasAlResumen()).toHaveLength(0)
  })

  it('el usuario de Consulta aterriza en «Reportes» (change 26, D11) y no ve la tarjeta ni «Revisión»', async () => {
    montar('CON')

    expect(await screen.findByText('Pantalla de reportes')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Para revisar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Revisión/ })).not.toBeInTheDocument()
    expect(llamadasAlResumen()).toHaveLength(0)
  })

  // Change 28, tarea 3.2 (D5): el aviso de consistencia aparece encima de «Para revisar» en el inicio.
  it('con VER_CONSISTENCIA y diferencias en la última verificación muestra el aviso junto a «Para revisar»', async () => {
    apiFetchMock.mockImplementation((ruta: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () =>
          ruta === '/sistema/consistencia'
            ? {
                ejecutada_en: '2026-11-10T05:00:00Z',
                resultado: 'CON_DIFERENCIAS',
                diferencias: [
                  {
                    tipo: 'STOCK_TOTAL',
                    cuenta_tipo: null,
                    entidad_id: null,
                    entidad_nombre: null,
                    saldo_materializado: null,
                    suma_del_libro: null,
                    producto_id: null,
                    producto_nombre: 'Vino A',
                    ubicacion_id: null,
                    ubicacion_nombre: null,
                    materializado: 9,
                    esperado: 5,
                    promedio_vigente: null,
                    promedio_historia: null,
                  },
                ],
              }
            : resumen(),
      }),
    )
    montar('ADM')

    const aviso = await screen.findByRole('alert')
    expect(within(aviso).getByText('Stock total de Vino A: guardado 9, suma de sus ubicaciones 5.')).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Para revisar' })).toBeInTheDocument()
  })
})
