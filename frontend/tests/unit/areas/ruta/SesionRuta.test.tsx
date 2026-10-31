import 'fake-indexeddb/auto'

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../../unit/utils/bootstrapDePrueba'

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  renovarSesion: vi.fn(),
  obtenerJornadaActual: vi.fn(),
  pedirBootstrap: vi.fn(),
  iniciarSesionConContrasena: vi.fn(),
  obtenerYo: vi.fn(),
}))

vi.mock('../../../../src/lib/api/httpClient', () => ({
  apiFetch: mocks.apiFetch,
  renovarSesion: mocks.renovarSesion,
}))
vi.mock('../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))
vi.mock('../../../../src/features/stock/api', () => ({ obtenerJornadaActual: mocks.obtenerJornadaActual }))
vi.mock('../../../../src/sync/clienteBootstrap', () => ({ pedirBootstrap: mocks.pedirBootstrap }))
vi.mock('../../../../src/features/identidad/login', () => ({
  iniciarSesionConContrasena: mocks.iniciarSesionConContrasena,
}))
vi.mock('../../../../src/features/identidad/api', () => ({ obtenerYo: mocks.obtenerYo }))

import { useSesionRutaActiva } from '../../../../src/areas/ruta/sesion/contextoSesion'
import { SesionRuta } from '../../../../src/areas/ruta/sesion/SesionRuta'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { definirPin } from '../../../../src/lib/sesionLocal/pin'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

const PIN = '482915'

function Inicio() {
  const { entrada } = useSesionRutaActiva()
  return <div>Inicio de prueba: {entrada.tipo}</div>
}

function montar() {
  return render(
    <SesionRuta>
      <Inicio />
    </SesionRuta>,
  )
}

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

async function sembrarSesionConDatos(opciones: { conPin?: boolean; jornadaId?: string } = {}) {
  const b = bootstrapDePrueba({ clientes: [clienteDePrueba(1, 'Almacén Norte')] })
  b.sesion.jornada.id = opciones.jornadaId ?? ID(2)
  await aplicarBootstrap(b)
  await baseLocal.meta.put({ clave: 'usuario_local_id', valor: ID(1) })
  if (opciones.conPin ?? true) await definirPin(PIN, PIN)
}

async function tipearPin(pin: string, boton = /desbloquear/i) {
  const u = userEvent.setup()
  await u.type(await screen.findByLabelText(/^PIN$/i), pin)
  await u.click(screen.getByRole('button', { name: boton }))
}

/**
 * Change 21, tareas 9.2 y 9.3 (spec `identidad/sesion-local`, "El PIN desbloquea la sesión local
 * con y sin conexión"; `design.md` D11, D14; SEG-03, ADR-017, RUT-03). Sin regla de segundo
 * plano: solo el arranque o la recarga piden el PIN.
 */
describe('SesionRuta: máquina de estados de /ruta (tareas 9.2 y 9.3)', () => {
  beforeEach(async () => {
    for (const m of Object.values(mocks)) m.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
    mocks.renovarSesion.mockResolvedValue('renovada')
    mocks.obtenerJornadaActual.mockResolvedValue(null)
    mocks.iniciarSesionConContrasena.mockResolvedValue({ access_token: 'tok' })
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sin sesión local muestra el inicio de sesión', async () => {
    montar()
    expect(await screen.findByRole('button', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(screen.queryByText(/inicio de prueba/i)).not.toBeInTheDocument()
  })

  it('login → definir PIN → bootstrap → inicio, guardando el usuario local y el PIN derivado', async () => {
    const jornada = { id: ID(2), estado: 'ABIERTA' }
    mocks.obtenerJornadaActual.mockResolvedValue(jornada)
    mocks.pedirBootstrap.mockResolvedValue({ tipo: 'ok', bootstrap: bootstrapDePrueba() })
    const u = userEvent.setup()
    montar()

    await u.type(await screen.findByLabelText(/organización/i), 'demo')
    await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor')
    await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
    await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    await u.type(await screen.findByLabelText(/^PIN$/i), PIN)
    await u.type(screen.getByLabelText(/repetí el PIN/i), PIN)
    await u.click(screen.getByRole('button', { name: /guardar PIN/i }))

    expect(await screen.findByText('Inicio de prueba: bootstrap_aplicado')).toBeInTheDocument()
    expect((await baseLocal.meta.get('usuario_local_id'))?.valor).toBe(ID(1))
    expect(await baseLocal.meta.get('pin_hash')).toBeDefined()
    expect((await baseLocal.meta.get('jornada_id'))?.valor).toBe(ID(2))
    expect(await baseLocal.clientes.count()).toBeGreaterThan(0)
  })

  it('un PIN trivial en la definición se rechaza con el motivo y no pasa al inicio', async () => {
    const u = userEvent.setup()
    montar()
    await u.type(await screen.findByLabelText(/organización/i), 'demo')
    await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor')
    await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
    await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    await u.type(await screen.findByLabelText(/^PIN$/i), '123456')
    await u.type(screen.getByLabelText(/repetí el PIN/i), '123456')
    await u.click(screen.getByRole('button', { name: /guardar PIN/i }))

    expect(await screen.findByText(/dígitos seguidos/i)).toBeInTheDocument()
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
  })

  it('arranque con sesión local: pide el PIN antes de mostrar nada', async () => {
    await sembrarSesionConDatos()
    montar()

    expect(await screen.findByLabelText(/^PIN$/i)).toBeInTheDocument()
    expect(screen.queryByText(/inicio de prueba/i)).not.toBeInTheDocument()
  }, 15_000)

  it('sin señal el PIN desbloquea sin ninguna petición a la red', async () => {
    conectado(false)
    await sembrarSesionConDatos()
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText('Inicio de prueba: sin_red')).toBeInTheDocument()
    expect(mocks.renovarSesion).not.toHaveBeenCalled()
    expect(mocks.obtenerJornadaActual).not.toHaveBeenCalled()
    expect(mocks.pedirBootstrap).not.toHaveBeenCalled()
    expect(mocks.apiFetch).not.toHaveBeenCalled()
  }, 15_000)

  it('con señal renueva el token y, con la misma jornada, no pide otro bootstrap', async () => {
    await sembrarSesionConDatos({ jornadaId: ID(2) })
    mocks.obtenerJornadaActual.mockResolvedValue({ id: ID(2), estado: 'ABIERTA' })
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText('Inicio de prueba: al_dia')).toBeInTheDocument()
    expect(mocks.renovarSesion).toHaveBeenCalledTimes(1)
    expect(mocks.pedirBootstrap).not.toHaveBeenCalled()
  }, 15_000)

  it('con señal y una jornada abierta distinta de la local pide y aplica el bootstrap', async () => {
    await sembrarSesionConDatos({ jornadaId: ID(2) })
    mocks.obtenerJornadaActual.mockResolvedValue({ id: ID(9), estado: 'ABIERTA' })
    const nuevo = bootstrapDePrueba({ clientes: [] })
    nuevo.sesion.jornada.id = ID(9)
    mocks.pedirBootstrap.mockResolvedValue({ tipo: 'ok', bootstrap: nuevo })
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText('Inicio de prueba: bootstrap_aplicado')).toBeInTheDocument()
    expect((await baseLocal.meta.get('jornada_id'))?.valor).toBe(ID(9))
    expect(await baseLocal.clientes.count()).toBe(0)
  }, 15_000)

  it('sin jornada abierta no pide bootstrap y el inicio sabe que puede ofrecer abrirla', async () => {
    await sembrarSesionConDatos()
    mocks.obtenerJornadaActual.mockResolvedValue(null)
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText('Inicio de prueba: sin_jornada')).toBeInTheDocument()
    expect(mocks.pedirBootstrap).not.toHaveBeenCalled()
  }, 15_000)

  it('un corte de red al consultar la jornada deja entrar con los datos locales', async () => {
    await sembrarSesionConDatos()
    mocks.obtenerJornadaActual.mockRejectedValue(new TypeError('Failed to fetch'))
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText('Inicio de prueba: sin_red')).toBeInTheDocument()
  }, 15_000)

  it('refresh rechazado: pide iniciar sesión y conserva la base local', async () => {
    await sembrarSesionConDatos()
    mocks.renovarSesion.mockResolvedValue('rechazada')
    montar()

    await tipearPin(PIN)

    expect(await screen.findByText(/tu sesión venció/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /iniciar sesión/i })).toBeInTheDocument()
    expect(await baseLocal.clientes.count()).toBe(1)
    expect(await baseLocal.meta.get('pin_hash')).toBeDefined()
  }, 15_000)

  it('tras el login del mismo usuario con PIN ya definido va al inicio sin redefinirlo', async () => {
    await sembrarSesionConDatos()
    mocks.renovarSesion.mockResolvedValue('rechazada')
    mocks.obtenerJornadaActual.mockResolvedValue({ id: ID(2), estado: 'ABIERTA' })
    montar()
    await tipearPin(PIN)
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText(/organización/i), 'demo')
    await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor')
    await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
    await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(await screen.findByText('Inicio de prueba: al_dia')).toBeInTheDocument()
  }, 20_000)

  it('un PIN incorrecto explica cuántos intentos quedan y sigue pidiendo el PIN', async () => {
    await sembrarSesionConDatos()
    montar()

    await tipearPin('000001')

    expect(await screen.findByText(/te quedan 9 intentos/i)).toBeInTheDocument()
    expect(screen.queryByText(/inicio de prueba/i)).not.toBeInTheDocument()
  }, 15_000)

  it('al agotar los intentos borra el PIN, pide iniciar sesión y conserva los datos', async () => {
    await sembrarSesionConDatos()
    await baseLocal.meta.put({ clave: 'pin_intentos', valor: '8' })
    montar()

    await tipearPin('000001')
    await screen.findByText(/te queda 1 intento/i)
    await tipearPin('000002')

    expect(await screen.findByText(/intentos del PIN/i)).toBeInTheDocument()
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
    expect(await baseLocal.clientes.count()).toBe(1)
    expect(mocks.renovarSesion).not.toHaveBeenCalled()
  }, 30_000)

  it('volver de segundo plano no pide el PIN, sin importar cuánto tiempo pasó (D14 = B)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    conectado(false)
    await sembrarSesionConDatos()
    vi.useRealTimers()
    montar()
    await tipearPin(PIN)
    await screen.findByText('Inicio de prueba: sin_red')

    vi.useFakeTimers({ toFake: ['Date'], now: Date.now() + 3 * 60 * 60 * 1000 })
    const ocultar = vi.spyOn(document, 'visibilityState', 'get')
    act(() => {
      ocultar.mockReturnValue('hidden')
      document.dispatchEvent(new Event('visibilitychange'))
    })
    act(() => {
      ocultar.mockReturnValue('visible')
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('focus'))
      window.dispatchEvent(new Event('pageshow'))
    })
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText(/inicio de prueba/i)).toBeInTheDocument())
    expect(screen.queryByLabelText(/^PIN$/i)).not.toBeInTheDocument()
  }, 20_000)

  it('una recarga (arranque nuevo) vuelve a pedir el PIN', async () => {
    conectado(false)
    await sembrarSesionConDatos()
    const primera = montar()
    await tipearPin(PIN)
    await screen.findByText('Inicio de prueba: sin_red')
    primera.unmount()

    montar()

    expect(await screen.findByLabelText(/^PIN$/i)).toBeInTheDocument()
  }, 20_000)
})
