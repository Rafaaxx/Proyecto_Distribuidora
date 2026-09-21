import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { navegarMock, apiFetchMock } = vi.hoisted(() => ({
  navegarMock: vi.fn(),
  apiFetchMock: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const real = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...real, useNavigate: () => navegarMock }
})

vi.mock('../../../../../src/lib/api/httpClient', () => ({
  apiFetch: apiFetchMock,
}))

vi.mock('../../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

import { LoginScreen } from '../../../../../src/areas/admin/auth/LoginScreen'

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LoginScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function respuesta(status: number, cuerpo: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => cuerpo,
  }
}

/**
 * Spec `identidad/autenticacion-y-sesion`, escenario "Contraseña incorrecta
 * no distingue de usuario inexistente" (tarea 13.4): el frontend no agrega
 * ninguna distinción propia -- solo muestra el mensaje que ya llega
 * indistinguible desde el backend.
 */
describe('LoginScreen (tarea 13.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    navegarMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra los campos de organización, usuario y contraseña', () => {
    renderPantalla()
    expect(screen.getByLabelText(/organización/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^usuario$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeInTheDocument()
  })

  it('no envía la petición si se manda el formulario vacío (validación de Zod)', async () => {
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findAllByRole('alert')).not.toHaveLength(0)
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('envía organización, usuario, contraseña y el dispositivo, y navega al listado tras iniciar sesión', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { access_token: 'token-emitido', token_type: 'bearer' }))
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.type(screen.getByLabelText(/organización/i), 'demo')
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'vendedor1')
    await usuarioEvento.type(screen.getByLabelText(/contraseña/i), 'correcta123')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    await waitFor(() => expect(navegarMock).toHaveBeenCalledWith('/admin/dispositivos'))

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    const [ruta, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/auth/login')
    const cuerpo = JSON.parse(opciones.body as string)
    expect(cuerpo).toEqual({
      organizacion_slug: 'demo',
      usuario: 'vendedor1',
      contrasena: 'correcta123',
      dispositivo_id: 'dispositivo-de-prueba',
      nombre_dispositivo: expect.any(String),
    })
  })

  it('muestra el mismo mensaje genérico tanto para contraseña incorrecta como para usuario inexistente', async () => {
    const mensajeIndistinguible = 'Usuario o contraseña incorrectos.'
    apiFetchMock.mockResolvedValueOnce(
      respuesta(401, { title: mensajeIndistinguible, codigo: 'IDENTIDAD_CREDENCIALES_INVALIDAS' }),
    )
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.type(screen.getByLabelText(/organización/i), 'demo')
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'vendedor1')
    await usuarioEvento.type(screen.getByLabelText(/contraseña/i), 'incorrecta')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findByText(mensajeIndistinguible)).toBeInTheDocument()

    apiFetchMock.mockResolvedValueOnce(
      respuesta(401, { title: mensajeIndistinguible, codigo: 'IDENTIDAD_CREDENCIALES_INVALIDAS' }),
    )
    await usuarioEvento.clear(screen.getByLabelText(/^usuario$/i))
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'no-existe')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    const mensajes = await screen.findAllByText(mensajeIndistinguible)
    expect(mensajes).toHaveLength(1)
    expect(navegarMock).not.toHaveBeenCalled()
  })
})
