import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { DispositivosScreen } from '../../../../../src/areas/admin/dispositivos/DispositivosScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DispositivosScreen />
    </QueryClientProvider>,
  )
}

const DISPOSITIVO_ACTIVO = {
  id: '11111111-1111-1111-1111-111111111111',
  nombre: 'Teléfono de Juan',
  prefijo: 'V01',
  estado: 'ACTIVO',
  ultimo_correlativo: 142,
  revocado_en: null,
}

const DISPOSITIVO_REVOCADO = {
  id: '22222222-2222-2222-2222-222222222222',
  nombre: 'Teléfono viejo',
  prefijo: 'V02',
  estado: 'REVOCADO',
  ultimo_correlativo: 5,
  revocado_en: '2026-01-01T00:00:00Z',
}

/**
 * Spec `identidad/dispositivos`. Tarea 13.5: la visibilidad de la pantalla
 * se apoya en la respuesta real del servidor (200 vs 403 de
 * `GET /identidad/dispositivos`, que ya exige `GESTIONAR_DISPOSITIVOS`,
 * tarea 10.7), no en una copia local del permiso -- ocultar en la interfaz
 * es cosmético (SEG-06), la validación real ya la hace el servidor en cada
 * petición, incluida la de revocar.
 */
describe('DispositivosScreen (tarea 13.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los dispositivos con su estado, prefijo y último correlativo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_ACTIVO, DISPOSITIVO_REVOCADO]))
    renderPantalla()

    const filaActiva = (await screen.findByText('Teléfono de Juan')).closest('tr')
    expect(filaActiva).not.toBeNull()
    expect(within(filaActiva as HTMLElement).getByText('V01')).toBeInTheDocument()
    expect(within(filaActiva as HTMLElement).getByText('ACTIVO')).toBeInTheDocument()
    expect(within(filaActiva as HTMLElement).getByText('142')).toBeInTheDocument()

    const filaRevocada = screen.getByText('Teléfono viejo').closest('tr')
    expect(within(filaRevocada as HTMLElement).getByText('REVOCADO')).toBeInTheDocument()
  })

  it('no muestra la tabla y explica la falta de permiso cuando el servidor responde 403', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
    )
    renderPantalla()

    expect(await screen.findByText(/no ten[eé]s permiso/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('el botón de revocar está deshabilitado para un dispositivo ya revocado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_REVOCADO]))
    renderPantalla()

    const fila = (await screen.findByText('Teléfono viejo')).closest('tr') as HTMLElement
    expect(within(fila).getByRole('button', { name: /revocar/i })).toBeDisabled()
  })

  it('revocar un dispositivo activo llama a DELETE y refresca el listado', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_ACTIVO]))
      .mockResolvedValueOnce(respuesta(204, undefined))
      .mockResolvedValueOnce(
        respuesta(200, [{ ...DISPOSITIVO_ACTIVO, estado: 'REVOCADO', revocado_en: '2026-01-02T00:00:00Z' }]),
      )

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    const fila = (await screen.findByText('Teléfono de Juan')).closest('tr') as HTMLElement
    await usuarioEvento.click(within(fila).getByRole('button', { name: /revocar/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(3))
    const [ruta, opciones] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    expect(ruta).toBe(`/identidad/dispositivos/${DISPOSITIVO_ACTIVO.id}`)
    expect(opciones.method).toBe('DELETE')

    await waitFor(() =>
      expect((screen.getByText('Teléfono de Juan').closest('tr') as HTMLElement).textContent).toContain(
        'REVOCADO',
      ),
    )
  })
})
