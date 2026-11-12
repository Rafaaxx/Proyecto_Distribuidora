/**
 * Change 20b, tarea 10.4 (D20; spec `identidad/autenticacion-y-sesion`; ADR-018, ADR-027, ADR-056,
 * ADR-057, INV-01, INV-06): pantalla "Mi contraseña" y el menú "Mi cuenta". Las contraseñas no se
 * guardan en ningún almacenamiento ni en la caché de consultas.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminLayout } from '../../../../../src/areas/admin/AdminLayout'
import MiContrasenaScreen from '../../../../../src/areas/admin/cuenta/MiContrasenaScreen'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ACTUAL = 'la-de-siempre-123'
const NUEVA = 'clave-nueva-2026'
const OTRA = 'otra-distinta-999'

let queryClient: QueryClient

function servidor(alCambiar?: ReglaDeApi['responder']) {
  enrutar(apiFetchMock, [
    { metodo: 'POST', ruta: '/yo/contrasena', responder: alCambiar ?? (() => ({ status: 204, cuerpo: null })) },
  ])
}

function montar(rol: RolDePrueba = 'VEN') {
  queryClient = queryClientConYo(rol)
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/mi-contrasena']}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="mi-contrasena" element={<MiContrasenaScreen />} />
            <Route path="mi-pin" element={<p>Pantalla Mi PIN</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function escribir(usuario: ReturnType<typeof userEvent.setup>, actual: string, nueva: string, confirmacion: string) {
  await usuario.type(await screen.findByLabelText('Tu contraseña actual'), actual)
  await usuario.type(screen.getByLabelText('Contraseña nueva'), nueva)
  await usuario.type(screen.getByLabelText('Repetí la contraseña nueva'), confirmacion)
}

const guardar = () => screen.getByRole('button', { name: 'Cambiar mi contraseña' })
const envios = () => llamadas(apiFetchMock, 'POST', '/yo/contrasena')
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('menú "Mi cuenta" (D20)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('el vendedor sin permisos de autorización ve "Mi cuenta" con solo "Mi contraseña"', async () => {
    servidor()
    montar('VEN')

    const menu = await screen.findByRole('navigation', { name: 'Mi cuenta' })
    expect(within(menu).getByRole('link', { name: 'Mi contraseña' })).toHaveAttribute('href', '/admin/mi-contrasena')
    expect(within(menu).queryByRole('link', { name: 'Mi PIN' })).not.toBeInTheDocument()
  })

  it('la supervisora ve "Mi PIN" y "Mi contraseña" bajo "Mi cuenta"', async () => {
    servidor()
    montar('SUP')

    const menu = await screen.findByRole('navigation', { name: 'Mi cuenta' })
    expect(within(menu).getByRole('link', { name: 'Mi PIN' })).toHaveAttribute('href', '/admin/mi-pin')
    expect(within(menu).getByRole('link', { name: 'Mi contraseña' })).toBeInTheDocument()
  })

  it.each(['ADM', 'GES', 'CON'] as const)('el rol %s también ve "Mi contraseña": es para todo usuario', async (rol) => {
    servidor()
    montar(rol)

    expect(await screen.findByRole('link', { name: 'Mi contraseña' })).toBeInTheDocument()
  })
})

describe('pantalla Mi contraseña (tarea 10.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('no pide nada al abrirse: solo ofrece el formulario', async () => {
    servidor()
    montar()

    await screen.findByLabelText('Tu contraseña actual')
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  describe('validación local (ayuda; el servidor valida igual)', () => {
    it('con la confirmación distinta no envía nada y lo dice junto al campo', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, NUEVA, OTRA)
      await usuario.click(guardar())

      expect(await screen.findByText(/las dos contraseñas tienen que ser iguales/i)).toBeInTheDocument()
      expect(envios()).toHaveLength(0)
    })

    it('con una contraseña nueva de menos de 8 caracteres no envía nada', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, 'corta', 'corta')
      await usuario.click(guardar())

      expect(await screen.findByText(/al menos 8 caracteres/i)).toBeInTheDocument()
      expect(envios()).toHaveLength(0)
    })

    it('sin la contraseña actual no envía nada', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await usuario.type(await screen.findByLabelText('Contraseña nueva'), NUEVA)
      await usuario.type(screen.getByLabelText('Repetí la contraseña nueva'), NUEVA)
      await usuario.click(guardar())

      expect(await screen.findByText(/escribí tu contraseña actual/i)).toBeInTheDocument()
      expect(envios()).toHaveLength(0)
    })
  })

  describe('envío (D20, ADR-056)', () => {
    it('envía la actual y la nueva con Operation-Id, sin la confirmación', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      await waitFor(() => expect(envios()).toHaveLength(1))
      const envio = envios()[0]!
      expect(JSON.parse(String(envio.init.body))).toEqual({ password_actual: ACTUAL, password_nueva: NUEVA })
      expect(operationId(envio)).toBeTruthy()
    })

    it('al terminar avisa que las otras sesiones se cerraron y limpia los tres campos', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      expect(await screen.findByText(/las demás sesiones abiertas se cerraron/i)).toBeInTheDocument()
      expect(screen.getByLabelText('Tu contraseña actual')).toHaveValue('')
      expect(screen.getByLabelText('Contraseña nueva')).toHaveValue('')
      expect(screen.getByLabelText('Repetí la contraseña nueva')).toHaveValue('')
    })

    it('las contraseñas no quedan en el almacenamiento, en la caché de consultas ni en las variables de la mutación', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())
      await screen.findByText(/las demás sesiones abiertas se cerraron/i)

      const todo = JSON.stringify({
        local: { ...window.localStorage },
        sesion: { ...window.sessionStorage },
        consultas: queryClient.getQueryCache().getAll().map((q) => q.state.data),
        mutaciones: queryClient.getMutationCache().getAll().map((m) => [m.state.variables, m.state.data]),
      })
      expect(todo).not.toContain(ACTUAL)
      expect(todo).not.toContain(NUEVA)
    })

    it('un segundo cambio después del éxito es otra operación (otro Operation-Id)', async () => {
      const usuario = userEvent.setup()
      servidor()
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())
      await screen.findByText(/las demás sesiones abiertas se cerraron/i)
      await escribir(usuario, NUEVA, OTRA, OTRA)
      await usuario.click(guardar())

      await waitFor(() => expect(envios()).toHaveLength(2))
      const [uno, dos] = envios()
      expect(operationId(uno!)).not.toBe(operationId(dos!))
    })
  })

  describe('rechazos explicados en palabras simples (D20)', () => {
    it.each([
      [403, 'IDENTIDAD_CONTRASENA_INCORRECTA', /la contraseña actual no es correcta/i],
      [429, 'IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS', /demasiados intentos/i],
      [422, 'IDENTIDAD_CONTRASENA_INVALIDA', /la contraseña nueva no sirve/i],
      [422, 'IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL', /distinta de la actual/i],
    ])('%s %s', async (status, codigo, texto) => {
      const usuario = userEvent.setup()
      servidor(() => ({ status, cuerpo: { title: 'Mensaje del servidor', codigo } }))
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      expect(await screen.findByText(texto)).toBeInTheDocument()
      expect(screen.queryByText(/las demás sesiones abiertas se cerraron/i)).not.toBeInTheDocument()
    })

    it('el bloqueo por intentos conserva el momento del desbloqueo que informa el servidor', async () => {
      const usuario = userEvent.setup()
      servidor(() => ({
        status: 429,
        cuerpo: { title: 'Podés volver a intentar a las 15:42.', codigo: 'IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS' },
      }))
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      expect(await screen.findByText(/a las 15:42/i)).toBeInTheDocument()
    })

    it('tras un rechazo, el reintento con la contraseña corregida reenvía el mismo Operation-Id', async () => {
      const usuario = userEvent.setup()
      let primera = true
      servidor(() => {
        if (primera) {
          primera = false
          return { status: 403, cuerpo: { title: 'x', codigo: 'IDENTIDAD_CONTRASENA_INCORRECTA' } }
        }
        return { status: 204, cuerpo: null }
      })
      montar()

      await escribir(usuario, 'equivocada-123', NUEVA, NUEVA)
      await usuario.click(guardar())
      await screen.findByText(/la contraseña actual no es correcta/i)
      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      await waitFor(() => expect(envios()).toHaveLength(2))
      const [uno, dos] = envios()
      expect(operationId(uno!)).toBe(operationId(dos!))
      expect(JSON.parse(String(dos!.init.body))).toEqual({ password_actual: ACTUAL, password_nueva: NUEVA })
    })

    it('un corte de red se explica y el reintento reenvía el mismo Operation-Id', async () => {
      const usuario = userEvent.setup()
      let cortar = true
      servidor(() => {
        if (cortar) throw new TypeError('Failed to fetch')
        return { status: 204, cuerpo: null }
      })
      montar()

      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())
      expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
      cortar = false
      await escribir(usuario, ACTUAL, NUEVA, NUEVA)
      await usuario.click(guardar())

      await screen.findByText(/las demás sesiones abiertas se cerraron/i)
      expect(new Set(envios().map(operationId)).size).toBe(1)
    })
  })
})
