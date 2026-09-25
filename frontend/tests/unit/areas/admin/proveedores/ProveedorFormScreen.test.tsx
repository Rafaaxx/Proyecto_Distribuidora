import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProveedorFormScreen } from '../../../../../src/areas/admin/proveedores/ProveedorFormScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Bodega Andina',
  cuit: null,
  contacto: null,
  telefono: null,
  email: null,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

function renderAlta() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/proveedores/nuevo']}>
        <Routes>
          <Route path="/admin/proveedores/nuevo" element={<ProveedorFormScreen />} />
          <Route path="/admin/proveedores/:proveedorId" element={<ProveedorFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderEdicion(proveedorId: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/proveedores/${proveedorId}`]}>
        <Routes>
          <Route path="/admin/proveedores/:proveedorId" element={<ProveedorFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Tarea 11.3: alta, nombre duplicado del servidor, y desactivar un
 * proveedor con productos activos (spec `administracion-de-proveedores`).
 */
describe('ProveedorFormScreen: alta (tarea 11.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('da de alta un proveedor con un único envío', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, PROVEEDOR))

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Bodega Andina')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear proveedor/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1))
    const [ruta, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/proveedores')
    expect(opciones.method).toBe('POST')
    expect(JSON.parse(String(opciones.body))).toMatchObject({ nombre: 'Bodega Andina' })
  })

  it('nombre duplicado informado por el servidor se muestra junto al campo y conserva lo cargado', async () => {
    apiFetchMock.mockImplementation(() =>
      Promise.resolve(respuesta(409, { title: 'El nombre ya está en uso.', codigo: 'NOMBRE_DUPLICADO' })),
    )

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Bodega Andina')
    await usuarioEvento.click(screen.getByRole('button', { name: /crear proveedor/i }))

    expect(await screen.findByText('El nombre ya está en uso.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Bodega Andina')
  })
})

describe('ProveedorFormScreen: ficha de edición (tarea 11.3, D5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('desactivar un proveedor con productos activos muestra el error y el proveedor sigue activo', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return Promise.resolve(
          respuesta(409, {
            title: 'El proveedor tiene productos activos.',
            codigo: 'PROVEEDOR_CON_PRODUCTOS_ACTIVOS',
          }),
        )
      }
      return Promise.resolve(respuesta(200, PROVEEDOR))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(PROVEEDOR.id)

    const botonDesactivar = await screen.findByRole('button', { name: /desactivar/i })
    await usuarioEvento.click(botonDesactivar)

    expect(await screen.findByText('El proveedor tiene productos activos.')).toBeInTheDocument()
    // El botón sigue ofreciendo "Desactivar": el proveedor sigue activo.
    expect(screen.getByRole('button', { name: /desactivar/i })).toBeInTheDocument()
  })

  it('desactivar un proveedor sin productos activos lo deja inactivo (ofrece "Reactivar")', async () => {
    let activo = true
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        activo = false
        return Promise.resolve(respuesta(200, { ...PROVEEDOR, activo }))
      }
      return Promise.resolve(respuesta(200, { ...PROVEEDOR, activo }))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion(PROVEEDOR.id)

    const botonDesactivar = await screen.findByRole('button', { name: /desactivar/i })
    await usuarioEvento.click(botonDesactivar)

    expect(await screen.findByRole('button', { name: /reactivar/i })).toBeInTheDocument()
  })
})
