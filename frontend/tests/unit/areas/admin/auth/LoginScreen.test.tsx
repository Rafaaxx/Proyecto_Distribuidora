import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { navegarMock, escrituraMock, yoMock } = vi.hoisted(() => ({
  navegarMock: vi.fn(),
  // Todo lo que no es `/yo` (el login mismo).
  escrituraMock: vi.fn(),
  // La consulta de sesión que la pantalla hace al montar para saber si ya hay sesión viva.
  yoMock: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const real = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...real, useNavigate: () => navegarMock }
})

vi.mock('../../../../../src/lib/api/httpClient', () => ({
  apiFetch: (ruta: string, init?: RequestInit) => (ruta === '/yo' ? yoMock() : escrituraMock(ruta, init)),
}))

vi.mock('../../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

import { LoginScreen } from '../../../../../src/areas/admin/auth/LoginScreen'
import { yoDePrueba } from '../../../utils/permisosDePrueba'

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
    escrituraMock.mockReset()
    navegarMock.mockReset()
    // Sin sesión viva por defecto: `/yo` responde 401.
    yoMock.mockReset()
    yoMock.mockResolvedValue(respuesta(401, { title: 'No autenticado.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('pone «Iniciar sesión» en el título de la pestaña', () => {
    renderPantalla()
    expect(document.title).toBe('Iniciar sesión · Distribuidora')
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
    expect(escrituraMock).not.toHaveBeenCalled()
  })

  it('envía organización, usuario, contraseña y el dispositivo, y navega al inicio de /admin tras iniciar sesión (tarea 7.6, B3)', async () => {
    escrituraMock.mockResolvedValueOnce(respuesta(200, { access_token: 'token-emitido', token_type: 'bearer' }))
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.type(screen.getByLabelText(/organización/i), 'demo')
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'vendedor1')
    await usuarioEvento.type(screen.getByLabelText(/contraseña/i), 'correcta123')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    // `design.md` D5-A (B3): el login ya no manda a `/admin/dispositivos`,
    // que solo Administración y Supervisor pueden usar (`01` §19), sino a la
    // ruta índice, que lleva a la primera sección permitida del usuario.
    await waitFor(() => expect(navegarMock).toHaveBeenCalledWith('/admin/inicio'))

    expect(escrituraMock).toHaveBeenCalledTimes(1)
    const [ruta, opciones] = escrituraMock.mock.calls[0] as [string, RequestInit]
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
    escrituraMock.mockResolvedValueOnce(
      respuesta(401, { title: mensajeIndistinguible, codigo: 'IDENTIDAD_CREDENCIALES_INVALIDAS' }),
    )
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await usuarioEvento.type(screen.getByLabelText(/organización/i), 'demo')
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'vendedor1')
    await usuarioEvento.type(screen.getByLabelText(/contraseña/i), 'incorrecta')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findByText(mensajeIndistinguible)).toBeInTheDocument()

    escrituraMock.mockResolvedValueOnce(
      respuesta(401, { title: mensajeIndistinguible, codigo: 'IDENTIDAD_CREDENCIALES_INVALIDAS' }),
    )
    await usuarioEvento.clear(screen.getByLabelText(/^usuario$/i))
    await usuarioEvento.type(screen.getByLabelText(/^usuario$/i), 'no-existe')
    await usuarioEvento.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    const mensajes = await screen.findAllByText(mensajeIndistinguible)
    expect(mensajes).toHaveLength(1)
    expect(navegarMock).not.toHaveBeenCalled()
  })

  it('si ya hay una sesión viva (/yo responde) no muestra el formulario: redirige a /admin/inicio', async () => {
    yoMock.mockResolvedValue(respuesta(200, yoDePrueba('GES')))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/login']}>
          <Routes>
            <Route path="/admin/login" element={<LoginScreen />} />
            <Route path="/admin/inicio" element={<p>Inicio de administración</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Inicio de administración')).toBeInTheDocument()
    expect(screen.queryByLabelText(/organización/i)).not.toBeInTheDocument()
  })

  it('sin sesión (/yo da 401) muestra el formulario y consulta /yo una sola vez', async () => {
    renderPantalla()

    expect(await screen.findByLabelText(/organización/i)).toBeInTheDocument()
    await waitFor(() => expect(yoMock).toHaveBeenCalled())
    expect(yoMock).toHaveBeenCalledTimes(1)
    expect(navegarMock).not.toHaveBeenCalled()
  })
})
