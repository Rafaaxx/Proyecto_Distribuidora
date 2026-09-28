import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { SiTienePermiso } from '../../../../src/features/identidad/SiTienePermiso'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const YO_ADMINISTRACION = {
  usuario: { id: '1', nombre: 'Ana' },
  organizacion: { id: '2', nombre: 'Organización inicial' },
  rol: { id: '3', nombre: 'Administración' },
  permisos: ['GESTIONAR_CATALOGO'],
}

/** Hijo que dispara una consulta al montarse: sirve para comprobar que,
 * sin el permiso, ni siquiera se monta (D4-A, tarea 6.4). */
const consultaDelHijoMock = vi.fn()
function HijoQuePide() {
  consultaDelHijoMock()
  return <p>Datos del hijo</p>
}

function renderConProveedor(hijo: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{hijo}</QueryClientProvider>)
}

describe('<SiTienePermiso> (tarea 6.4, design.md D4-A)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    consultaDelHijoMock.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('mientras carga, muestra el nodo "cargando" y no monta los hijos', () => {
    apiFetchMock.mockReturnValue(new Promise(() => {}))
    renderConProveedor(
      <SiTienePermiso permiso="GESTIONAR_CATALOGO" cargando={<p>Cargando…</p>}>
        <HijoQuePide />
      </SiTienePermiso>,
    )

    expect(screen.getByText('Cargando…')).toBeInTheDocument()
    expect(screen.queryByText('Datos del hijo')).not.toBeInTheDocument()
    expect(consultaDelHijoMock).not.toHaveBeenCalled()
  })

  it('con el permiso, muestra los hijos', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    renderConProveedor(
      <SiTienePermiso permiso="GESTIONAR_CATALOGO">
        <HijoQuePide />
      </SiTienePermiso>,
    )

    expect(await screen.findByText('Datos del hijo')).toBeInTheDocument()
    expect(consultaDelHijoMock).toHaveBeenCalledTimes(1)
  })

  it('sin el permiso, muestra el fallback y los hijos no se montan ni piden sus datos', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    renderConProveedor(
      <SiTienePermiso permiso="GESTIONAR_DISPOSITIVOS" fallback={<p>No tenés permiso.</p>}>
        <HijoQuePide />
      </SiTienePermiso>,
    )

    expect(await screen.findByText('No tenés permiso.')).toBeInTheDocument()
    expect(screen.queryByText('Datos del hijo')).not.toBeInTheDocument()
    expect(consultaDelHijoMock).not.toHaveBeenCalled()
    // El único pedido fue `/yo`: el hijo nunca llegó a pedir sus datos.
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(apiFetchMock).toHaveBeenCalledWith('/yo')
  })

  it('sin el permiso y sin fallback, no muestra nada', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    const { container } = renderConProveedor(
      <SiTienePermiso permiso="GESTIONAR_DISPOSITIVOS">
        <HijoQuePide />
      </SiTienePermiso>,
    )

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    await waitFor(() => expect(container.textContent).toBe(''))
    expect(consultaDelHijoMock).not.toHaveBeenCalled()
  })
})
