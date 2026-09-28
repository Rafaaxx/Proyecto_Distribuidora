import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { DispositivosScreen } from '../../../../../src/areas/admin/dispositivos/DispositivosScreen'
import type { RolDePrueba } from '../../../utils/permisosDePrueba'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

/**
 * Monta la pantalla con `['yo']` ya sembrado (auxiliar compartido de la
 * tarea 6.7), así el permiso de la prueba sale de la consulta de sesión y
 * no de un `apiFetch` interceptado. Con el permiso sembrado no se hace
 * ninguna petición a `/yo` (ADR-027: una consulta por sesión).
 *
 * El 403 del servidor se sigue simulando por `apiFetch`, porque ahora es
 * solo la red de seguridad: el permiso lo decide `['yo']`.
 */
function renderPantalla(rol: RolDePrueba = 'SUP') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
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

const SIN_PERMISO_DE_DISPOSITIVOS = 'No tenés permiso para gestionar dispositivos.'

/**
 * Spec `identidad/permisos-efectivos`, requisito "Las pantallas de
 * `/admin` deciden qué mostrar solo con los permisos efectivos"
 * (tarea 8.1, **B2**). Los tres escenarios de la spec están aquí: entrar
 * por URL sin permiso, entrar con el permiso, y el 403 del servidor entre
 * dos renovaciones del token. Los roles son los de `01-dominio.md` §19
 * (columnas SUP y GES).
 *
 * Linea base de la suite: 4 casos, todos verdes antes de la tarea 8.1.
 */
describe('DispositivosScreen (tarea 8.1, B2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los dispositivos con su estado, prefijo y último correlativo (escenario "Con el permiso, la pantalla muestra sus datos y acciones")', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_ACTIVO, DISPOSITIVO_REVOCADO]))
    renderPantalla('SUP')

    const filaActiva = (await screen.findByText('Teléfono de Juan')).closest('tr')
    expect(filaActiva).not.toBeNull()
    expect(within(filaActiva as HTMLElement).getByText('V01')).toBeInTheDocument()
    expect(within(filaActiva as HTMLElement).getByText('ACTIVO')).toBeInTheDocument()
    expect(within(filaActiva as HTMLElement).getByText('142')).toBeInTheDocument()

    const filaRevocada = screen.getByText('Teléfono viejo').closest('tr')
    expect(within(filaRevocada as HTMLElement).getByText('REVOCADO')).toBeInTheDocument()
  })

  it('con el permiso sembrado no hace ninguna petición extra a /yo (ADR-027: una consulta por sesión)', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_ACTIVO]))
    renderPantalla('SUP')

    expect(await screen.findByText('Teléfono de Juan')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/yo')
  })

  it('al entrar por URL sin el permiso muestra que falta y NO pide el listado de dispositivos (B2, escenario "Entrar por URL a una pantalla sin permiso no consulta sus datos")', async () => {
    renderPantalla('GES')

    expect(await screen.findByText(SIN_PERMISO_DE_DISPOSITIVOS)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un 403 del servidor entre dos renovaciones se muestra como falta de permiso, sin listado y sin error genérico (red de seguridad, SEG-06)', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
    )
    renderPantalla('SUP')

    expect(await screen.findByText(SIN_PERMISO_DE_DISPOSITIVOS)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/no se pudieron obtener los dispositivos/i)).not.toBeInTheDocument()
  })

  it('el botón de revocar está deshabilitado para un dispositivo ya revocado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [DISPOSITIVO_REVOCADO]))
    renderPantalla('SUP')

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
    renderPantalla('SUP')

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
