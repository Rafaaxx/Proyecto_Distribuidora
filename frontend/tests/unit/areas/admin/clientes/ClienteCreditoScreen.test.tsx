import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ClienteCreditoScreen } from '../../../../../src/areas/admin/clientes/ClienteCreditoScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CLIENTE = {
  id: '11111111-1111-4111-8111-111111111111',
  codigo: null,
  nombre: 'Kiosco La Esquina',
  razon_social: null,
  documento_tipo: null,
  documento_numero: null,
  direccion: 'Av. San Martín 1420',
  contacto: 'Rocío',
  telefono: null,
  email: null,
  lista_precio_id: null,
  limite_credito: null,
  politica_credito: null,
  tolerancia_offline_tipo: null,
  tolerancia_offline_valor: null,
  estado_facturacion_default: null,
  es_consumidor_final: false,
  estado: 'ACTIVO',
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const SIN_PERMISO_DE_CREDITO = 'No tenés permiso para gestionar el crédito de clientes.'

function renderCredito(queryClient: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/clientes/${CLIENTE.id}/credito`]}>
        <Routes>
          <Route path="/admin/clientes/:clienteId/credito" element={<ClienteCreditoScreen />} />
          <Route path="/admin/clientes/:clienteId" element={<p>Ficha de cliente</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ClienteCreditoScreen (tarea 5.4, D3, D8)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('modifica el límite de crédito con un único envío PUT a la ruta de crédito', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CLIENTE, limite_credito: '150000.00' }))
      }
      return Promise.resolve(respuesta(200, CLIENTE))
    })

    const usuarioEvento = userEvent.setup()
    renderCredito()

    const campoLimite = await screen.findByLabelText(/límite de crédito/i)
    await usuarioEvento.type(campoLimite, '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar crédito/i }))

    await waitFor(() => {
      const llamadaPut = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')
      expect(llamadaPut).toBeDefined()
    })
    const [ruta, opciones] = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT') as [
      string,
      RequestInit,
    ]
    expect(ruta).toBe(`/clientes/${CLIENTE.id}/credito`)
    expect(JSON.parse(String(opciones.body))).toMatchObject({ limite_credito: '150000.00' })
  })

  it('muestra "Hereda de la organización" cuando el límite vigente es null', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, CLIENTE))

    renderCredito()

    const [textoVigente] = await screen.findAllByText(/hereda de la organización/i)
    expect(textoVigente.tagName).toBe('STRONG')
  })

  it('el consumidor final rechazado por el servidor muestra CONSUMIDOR_FINAL_SIN_CREDITO junto al campo', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(
          respuesta(422, {
            title: 'El consumidor final no admite crédito propio.',
            codigo: 'CONSUMIDOR_FINAL_SIN_CREDITO',
          }),
        )
      }
      return Promise.resolve(respuesta(200, { ...CLIENTE, es_consumidor_final: true, limite_credito: '0.00' }))
    })

    const usuarioEvento = userEvent.setup()
    renderCredito()

    const campoLimite = await screen.findByLabelText(/límite de crédito/i)
    await usuarioEvento.clear(campoLimite)
    await usuarioEvento.type(campoLimite, '50000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar crédito/i }))

    expect(await screen.findByText('El consumidor final no admite crédito propio.')).toBeInTheDocument()
  })

  it('sin GESTIONAR_CREDITO no pide el cliente y muestra que falta el permiso', async () => {
    renderCredito(queryClientConYo('GES', { permisos: ['GESTIONAR_CLIENTES'] }))

    expect(await screen.findByText(SIN_PERMISO_DE_CREDITO)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  /** Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): guardar el
   * crédito vuelve a la ficha del cliente, no se queda en la pantalla de
   * crédito. */
  it('después de guardar el crédito vuelve a la ficha del cliente', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CLIENTE, limite_credito: '150000.00' }))
      }
      return Promise.resolve(respuesta(200, CLIENTE))
    })

    const usuarioEvento = userEvent.setup()
    renderCredito()

    const campoLimite = await screen.findByLabelText(/límite de crédito/i)
    await usuarioEvento.type(campoLimite, '150000.00')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar crédito/i }))

    expect(await screen.findByText('Ficha de cliente')).toBeInTheDocument()
  })
})
