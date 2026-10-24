/**
 * Change 18b, tarea 14.3 (D21 parte B): pantalla "Mi PIN" (spec `identidad/pin-de-autorizacion`;
 * SEG-05, ADR-011, ADR-018, ADR-019, ADR-027, INV-06). Los secretos no se persisten en ningún
 * almacenamiento.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminLayout } from '../../../../../src/areas/admin/AdminLayout'
import MiPinScreen from '../../../../../src/areas/admin/cuenta/MiPinScreen'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const PIN = '482913'
const CLAVE = 'clave-de-marta-2026'

function servidor(opciones: { puedeDefinir?: boolean; alDefinir?: ReglaDeApi['responder'] } = {}) {
  let tienePin = false
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: '/yo/pin-autorizacion',
      responder: () => ({
        status: 200,
        cuerpo: { puede_definir: opciones.puedeDefinir ?? true, tiene_pin_autorizacion: tienePin },
      }),
    },
    {
      metodo: 'POST',
      ruta: '/yo/pin-autorizacion',
      responder: (url, init) => {
        if (opciones.alDefinir) return opciones.alDefinir(url, init)
        tienePin = true
        return { status: 204, cuerpo: null }
      },
    },
  ])
}

function renderPantalla(rol: RolDePrueba = 'SUP') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/mi-pin']}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="mi-pin" element={<MiPinScreen />} />
            <Route path="catalogo" element={<p>Catálogo</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function escribir(usuario: ReturnType<typeof userEvent.setup>, password: string, pin: string, repeticion: string) {
  await usuario.type(await screen.findByLabelText(/tu contraseña actual/i), password)
  await usuario.type(screen.getByLabelText(/^pin nuevo$/i), pin)
  await usuario.type(screen.getByLabelText(/repetí el pin/i), repeticion)
}

const guardar = () => screen.getByRole('button', { name: /guardar mi pin/i })

describe('Mi PIN (tarea 14.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  // Escenarios de la spec: la entrada solo con permiso de autorización
  it('la supervisora ve "Mi PIN" en el menú de la sesión; el vendedor no la ve', async () => {
    servidor()
    renderPantalla('SUP')
    expect(await screen.findByRole('link', { name: /^mi pin$/i })).toBeInTheDocument()
  })

  it('un vendedor sin permisos de autorización no ve la entrada ni la pantalla pide nada (ADR-027)', () => {
    servidor()
    renderPantalla('VEN')

    expect(screen.queryByRole('link', { name: /^mi pin$/i })).not.toBeInTheDocument()
    expect(screen.getByText(/tu rol no permite autorizar excepciones/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/yo/pin-autorizacion')).toHaveLength(0)
  })

  it('muestra "PIN definido: No" y, tras definirlo, "Sí"; el anterior deja de servir (se avisa)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()

    expect(await screen.findByTestId('pin-definido')).toHaveTextContent('PIN definido: No')
    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())

    expect(await screen.findByText(/tu pin quedó guardado/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('pin-definido')).toHaveTextContent('PIN definido: Sí'))
    const envios = llamadas(apiFetchMock, 'POST', '/yo/pin-autorizacion')
    expect(envios).toHaveLength(1)
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ pin: PIN, password_actual: CLAVE })
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
  })

  it('contraseña y PIN van enmascarados y se borran de la pantalla al enviar', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, CLAVE, PIN, PIN)
    expect(screen.getByLabelText(/tu contraseña actual/i)).toHaveAttribute('type', 'password')
    expect(screen.getByLabelText(/^pin nuevo$/i)).toHaveAttribute('type', 'password')
    expect(screen.getByLabelText(/repetí el pin/i)).toHaveAttribute('type', 'password')

    await usuario.click(guardar())
    await screen.findByText(/tu pin quedó guardado/i)
    expect(screen.getByLabelText(/tu contraseña actual/i)).toHaveValue('')
    expect(screen.getByLabelText(/^pin nuevo$/i)).toHaveValue('')
    expect(screen.getByLabelText(/repetí el pin/i)).toHaveValue('')
  })

  it('validación local: PIN corto, distinto en las dos veces o sin contraseña no se envían', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, CLAVE, '123', '123')
    await usuario.click(guardar())
    expect(await screen.findByText(/al menos 6 números/i)).toBeInTheDocument()

    await usuario.clear(screen.getByLabelText(/^pin nuevo$/i))
    await usuario.clear(screen.getByLabelText(/repetí el pin/i))
    await usuario.type(screen.getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.type(screen.getByLabelText(/repetí el pin/i), '482914')
    await usuario.click(guardar())
    expect(await screen.findByText(/tienen que ser iguales/i)).toBeInTheDocument()

    await usuario.clear(screen.getByLabelText(/repetí el pin/i))
    await usuario.type(screen.getByLabelText(/repetí el pin/i), PIN)
    await usuario.clear(screen.getByLabelText(/tu contraseña actual/i))
    await usuario.click(guardar())
    expect(await screen.findByText(/escribí tu contraseña actual/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/yo/pin-autorizacion')).toHaveLength(0)
  })

  // Escenario: contraseña incorrecta
  it('IDENTIDAD_CONTRASENA_INCORRECTA: "La contraseña no es correcta", los secretos se borraron y el reintento usa el mismo Operation-Id', async () => {
    let intento = 0
    servidor({
      alDefinir: () => {
        intento += 1
        return intento === 1
          ? { status: 403, cuerpo: { title: 'La contraseña no es correcta.', codigo: 'IDENTIDAD_CONTRASENA_INCORRECTA' } }
          : { status: 204, cuerpo: null }
      },
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, 'otra-clave-mala', PIN, PIN)
    await usuario.click(guardar())

    expect(await screen.findByText('La contraseña no es correcta.')).toBeInTheDocument()
    expect(screen.getByLabelText(/tu contraseña actual/i)).toHaveValue('')
    expect(screen.getByLabelText(/^pin nuevo$/i)).toHaveValue('')

    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())
    await screen.findByText(/tu pin quedó guardado/i)
    const envios = llamadas(apiFetchMock, 'POST', '/yo/pin-autorizacion')
    expect(envios).toHaveLength(2)
    const idDe = (i: number) => new Headers(envios[i]?.init.headers).get('Operation-Id')
    expect(idDe(0)).toBe(idDe(1))
    expect(JSON.parse(String(envios[1]?.init.body))).toEqual({ pin: PIN, password_actual: CLAVE })
  })

  it('cada envío limpia los errores anteriores: contraseña incorrecta y luego un fallo local muestra solo el actual', async () => {
    servidor({
      alDefinir: () => ({ status: 403, cuerpo: { title: 'La contraseña no es correcta.', codigo: 'IDENTIDAD_CONTRASENA_INCORRECTA' } }),
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, 'otra-clave-mala', PIN, PIN)
    await usuario.click(guardar())
    expect(await screen.findByText('La contraseña no es correcta.')).toBeInTheDocument()

    // Reenvía sin contraseña: el problema actual es otro (falta la contraseña).
    await usuario.type(screen.getByLabelText(/^pin nuevo$/i), PIN)
    await usuario.type(screen.getByLabelText(/repetí el pin/i), PIN)
    await usuario.click(guardar())
    expect(await screen.findByText(/escribí tu contraseña actual/i)).toBeInTheDocument()
    expect(screen.queryByText('La contraseña no es correcta.')).not.toBeInTheDocument()

    // Reenvía con PIN corto: solo el error de PIN.
    await usuario.type(screen.getByLabelText(/tu contraseña actual/i), CLAVE)
    await usuario.clear(screen.getByLabelText(/^pin nuevo$/i))
    await usuario.clear(screen.getByLabelText(/repetí el pin/i))
    await usuario.type(screen.getByLabelText(/^pin nuevo$/i), '123')
    await usuario.type(screen.getByLabelText(/repetí el pin/i), '123')
    await usuario.click(guardar())
    expect(await screen.findByText(/al menos 6 números/i)).toBeInTheDocument()
    expect(screen.queryByText(/escribí tu contraseña actual/i)).not.toBeInTheDocument()
    expect(screen.queryByText('La contraseña no es correcta.')).not.toBeInTheDocument()
  })

  it('un envío exitoso tras un rechazo no deja errores viejos', async () => {
    let intento = 0
    servidor({
      alDefinir: () => {
        intento += 1
        return intento === 1
          ? { status: 403, cuerpo: { title: 'La contraseña no es correcta.', codigo: 'IDENTIDAD_CONTRASENA_INCORRECTA' } }
          : { status: 204, cuerpo: null }
      },
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, 'mala', PIN, PIN)
    await usuario.click(guardar())
    await screen.findByText('La contraseña no es correcta.')
    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())

    await screen.findByText(/tu pin quedó guardado/i)
    expect(screen.queryByText('La contraseña no es correcta.')).not.toBeInTheDocument()
  })

  it('IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS muestra el mensaje del servidor con el momento del desbloqueo', async () => {
    servidor({
      alDefinir: () => ({
        status: 429,
        cuerpo: { title: 'Demasiados intentos. Desbloqueo: 10:25.', codigo: 'IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS' },
      }),
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())

    expect(await screen.findByText('Demasiados intentos. Desbloqueo: 10:25.')).toBeInTheDocument()
    expect(screen.queryByText(/tu pin quedó guardado/i)).not.toBeInTheDocument()
  })

  it('IDENTIDAD_PIN_AUTORIZACION_INVALIDO explica que no puede ser fácil de adivinar', async () => {
    servidor({
      alDefinir: () => ({
        status: 422,
        cuerpo: { title: 'PIN inválido.', codigo: 'IDENTIDAD_PIN_AUTORIZACION_INVALIDO' },
      }),
    })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, CLAVE, '123456', '123456')
    await usuario.click(guardar())

    expect(await screen.findByText(/no puede ser fácil de adivinar, como 123456 o 111111/i)).toBeInTheDocument()
  })

  it('PERMISO_REQUERIDO (403 sin código de negocio) se explica', async () => {
    servidor({ alDefinir: () => ({ status: 403, cuerpo: { title: 'Falta permiso.' } }) })
    const usuario = userEvent.setup()
    renderPantalla()
    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())

    expect(await screen.findByText('No tenés permiso para hacer esto.')).toBeInTheDocument()
  })

  it('si el servidor dice que el rol no puede definir PIN, no ofrece el formulario', async () => {
    servidor({ puedeDefinir: false })
    renderPantalla()

    expect(await screen.findByText(/tu rol no permite autorizar excepciones/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/tu contraseña actual/i)).not.toBeInTheDocument()
  })

  it('la contraseña y el PIN no quedan en ningún almacenamiento del navegador', async () => {
    servidor()
    const usuario = userEvent.setup()
    const escrituras: string[] = []
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation((clave, valor) => {
      escrituras.push(`${clave}=${valor}`)
    })
    renderPantalla()
    await escribir(usuario, CLAVE, PIN, PIN)
    await usuario.click(guardar())
    await screen.findByText(/tu pin quedó guardado/i)

    expect(escrituras.some((e) => e.includes(PIN) || e.includes(CLAVE))).toBe(false)
    const guardado = JSON.stringify({ ...window.localStorage, ...window.sessionStorage })
    expect(guardado).not.toContain(PIN)
    expect(guardado).not.toContain(CLAVE)
    setItem.mockRestore()
  })

  it('tiene su ayuda "(?)" (cuenta.miPin)', async () => {
    servidor()
    renderPantalla()
    expect(await screen.findByRole('button', { name: /ayuda: mi pin/i })).toBeInTheDocument()
  })
})
