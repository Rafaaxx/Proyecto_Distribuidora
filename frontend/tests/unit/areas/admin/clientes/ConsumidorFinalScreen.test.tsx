import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ConsumidorFinalScreen } from '../../../../../src/areas/admin/clientes/ConsumidorFinalScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CONSUMIDOR_FINAL = {
  id: '22222222-2222-4222-8222-222222222222',
  codigo: null,
  nombre: 'Consumidor final',
  razon_social: null,
  documento_tipo: null,
  documento_numero: null,
  direccion: 'N/A',
  contacto: 'N/A',
  telefono: null,
  email: null,
  lista_precio_id: null,
  limite_credito: '0.00',
  politica_credito: null,
  tolerancia_offline_tipo: null,
  tolerancia_offline_valor: null,
  estado_facturacion_default: null,
  es_consumidor_final: true,
  estado: 'ACTIVO',
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const SIN_PERMISO_DE_CONFIGURACION = 'No tenés permiso para configurar la organización.'

function renderPantalla(queryClient: QueryClient = queryClientConYo('ADM')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/clientes/consumidor-final']}>
        <Routes>
          <Route path="/admin/clientes/consumidor-final" element={<ConsumidorFinalScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ConsumidorFinalScreen (tarea 5.5, D4, ADR-029)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin habilitar muestra el formulario y lo habilita con un único envío POST', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(respuesta(201, CONSUMIDOR_FINAL))
      }
      return Promise.resolve(respuesta(200, { habilitado: false, cliente: null }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('button', { name: /habilitar consumidor final/i })
    await usuarioEvento.click(screen.getByRole('button', { name: /habilitar consumidor final/i }))

    await waitFor(() => {
      const llamadaPost = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'POST')
      expect(llamadaPost).toBeDefined()
    })
    const [ruta, opciones] = apiFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'POST') as [
      string,
      RequestInit,
    ]
    expect(ruta).toBe('/clientes/consumidor-final')
    expect((opciones.headers as Record<string, string>)['Operation-Id']).toBeTruthy()
    expect(JSON.parse(String(opciones.body))).toMatchObject({ nombre: 'Consumidor final' })
  })

  it('ya habilitado muestra el cliente y no el formulario', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { habilitado: true, cliente: CONSUMIDOR_FINAL }))

    renderPantalla()

    expect(await screen.findByRole('link', { name: /ver ficha/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /habilitar consumidor final/i })).not.toBeInTheDocument()
  })

  it('habilitar dos veces muestra CONSUMIDOR_FINAL_YA_HABILITADO', async () => {
    apiFetchMock.mockImplementation((_ruta: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(
          respuesta(409, {
            title: 'El consumidor final ya está habilitado.',
            codigo: 'CONSUMIDOR_FINAL_YA_HABILITADO',
          }),
        )
      }
      return Promise.resolve(respuesta(200, { habilitado: false, cliente: null }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.click(await screen.findByRole('button', { name: /habilitar consumidor final/i }))

    expect(await screen.findByText('El consumidor final ya está habilitado.')).toBeInTheDocument()
  })

  it('sin ADMIN_CONFIGURACION no pide nada y muestra que falta el permiso', async () => {
    renderPantalla(queryClientConYo('GES'))

    expect(await screen.findByText(SIN_PERMISO_DE_CONFIGURACION)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
