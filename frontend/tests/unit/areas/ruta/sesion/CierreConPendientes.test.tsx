import 'fake-indexeddb/auto'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ID } from '../../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { sembrarVenta } from '../../../utils/sembrarVenta'

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  renovarSesion: vi.fn(),
  obtenerYo: vi.fn(),
  iniciarSesionConContrasena: vi.fn(),
  obtenerJornadaActual: vi.fn(),
  pedirBootstrap: vi.fn(),
}))

vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: mocks.apiFetch, renovarSesion: mocks.renovarSesion }))
vi.mock('../../../../../src/features/identidad/api', () => ({ obtenerYo: mocks.obtenerYo }))
vi.mock('../../../../../src/features/identidad/login', () => ({ iniciarSesionConContrasena: mocks.iniciarSesionConContrasena }))
vi.mock('../../../../../src/features/stock/api', () => ({ obtenerJornadaActual: mocks.obtenerJornadaActual }))
vi.mock('../../../../../src/sync/clienteBootstrap', () => ({ pedirBootstrap: mocks.pedirBootstrap }))
vi.mock('../../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'disp-1'),
}))

import { registrarUsuarioTrasLogin } from '../../../../../src/areas/ruta/sesion/arranque'
import { CerrarSesionBoton } from '../../../../../src/areas/ruta/sesion/CerrarSesionBoton'
import { SesionRuta } from '../../../../../src/areas/ruta/sesion/SesionRuta'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { definirPin } from '../../../../../src/lib/sesionLocal/pin'
import { borrarSesionLocal } from '../../../../../src/lib/sesionLocal/sesionLocal'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'

/**
 * Change 22a, tarea 14.1 (spec `ruta/area-de-ruta`, "Cerrar sesión con ventas sin enviar avisa y
 * no borra"; `design.md` D16; cita SEG-03, SYN-09, `02` §6.4): al cerrar sesión se avisa cuántas
 * ventas quedan guardadas; confirmado, la sesión se cierra y las ventas siguen; otro usuario que
 * inicia sesión ve el aviso de las ventas pendientes del anterior y tampoco las borra.
 */
function respuesta(status: number) {
  return { ok: status >= 200 && status < 300, status, json: async () => ({}) }
}

async function contarOperaciones() {
  return {
    ventas: await baseLocal.ventas.count(),
    cola: await baseLocal.cola.count(),
    movimientos: await baseLocal.movimientos_locales.count(),
  }
}

describe('Cerrar sesión con ventas sin enviar (tarea 14.1, D16)', () => {
  beforeEach(async () => {
    for (const m of Object.values(mocks)) m.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await aplicarBootstrap(bootstrapParaVender())
    await baseLocal.meta.put({ clave: 'usuario_local_id', valor: ID(1) })
    await definirPin('482915', '482915')
    mocks.apiFetch.mockResolvedValue(respuesta(204))
  })

  afterEach(() => vi.restoreAllMocks())

  it('con una venta sin enviar avisa con el texto de la spec y, si confirma, cierra y la venta sigue', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    const antes = await contarOperaciones()
    const alCerrar = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={alCerrar} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    expect(
      await screen.findByText(
        'Tenés 1 venta sin enviar. Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos.',
      ),
    ).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: /^confirmar$/i }))

    await waitFor(() => expect(alCerrar).toHaveBeenCalledTimes(1))
    expect(await contarOperaciones()).toEqual(antes)
    expect(await baseLocal.ventas.get('venta-a')).toMatchObject({ estado_envio: 'PENDIENTE' })
    expect(await baseLocal.clientes.count()).toBe(0)
  })

  it('con varias ventas usa el plural', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 0, unidades: 2 })
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))

    expect(
      await screen.findByText(
        'Tenés 2 ventas sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.',
      ),
    ).toBeInTheDocument()
  })

  it('sin ventas sin enviar no agrega ningún aviso de pendientes', async () => {
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))

    expect(await screen.findByRole('dialog', { name: 'Cerrar sesión' })).toBeInTheDocument()
    expect(screen.queryByText(/sin enviar/i)).not.toBeInTheDocument()
  })

  it('cancelar el aviso no cierra la sesión ni toca la venta', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    const alCerrar = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={alCerrar} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    await u.click(await screen.findByRole('button', { name: /^cancelar$/i }))

    expect(alCerrar).not.toHaveBeenCalled()
    expect(mocks.apiFetch).not.toHaveBeenCalled()
    expect(await baseLocal.ventas.count()).toBe(1)
  })
})

describe('Otro usuario inicia sesión en el teléfono (tarea 14.1, D16, `02` §6.4)', () => {
  beforeEach(async () => {
    for (const m of Object.values(mocks)) m.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await aplicarBootstrap(bootstrapParaVender())
    await baseLocal.meta.put({ clave: 'usuario_local_id', valor: ID(1) })
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    mocks.renovarSesion.mockResolvedValue('renovada')
    mocks.obtenerJornadaActual.mockResolvedValue(null)
    mocks.iniciarSesionConContrasena.mockResolvedValue({ access_token: 'tok' })
  })

  afterEach(() => vi.restoreAllMocks())

  it('el registro tras el login informa las pendientes de vendedor y no las borra', async () => {
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(90), nombre: 'Vendedor Dos' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r.cambioDeUsuario).toBe(true)
    expect(r.pendientesDeOtro).toEqual([{ vendedor: 'Vendedor Uno', cantidad: 1 }])
    expect(await baseLocal.ventas.count()).toBe(1)
    expect(await baseLocal.cola.count()).toBe(1)
    expect(await baseLocal.clientes.count()).toBe(0)
  })

  it('el mismo usuario que vuelve a entrar no recibe aviso de otro', async () => {
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r.cambioDeUsuario).toBe(false)
    expect(r.pendientesDeOtro).toEqual([])
  })

  it('tras cerrar sesión (sin usuario local) otro usuario que entra recibe el aviso y no se borran', async () => {
    await borrarSesionLocal()
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(90), nombre: 'Vendedor Dos' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r.cambioDeUsuario).toBe(false)
    expect(r.pendientesDeOtro).toEqual([{ vendedor: 'Vendedor Uno', cantidad: 1 }])
    expect(await baseLocal.ventas.count()).toBe(1)
    expect(await baseLocal.cola.count()).toBe(1)
  })

  it('tras cerrar sesión, el mismo vendedor que vuelve a entrar no recibe aviso', async () => {
    await borrarSesionLocal()
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r.pendientesDeOtro).toEqual([])
    expect(await baseLocal.ventas.count()).toBe(1)
  })

  it('en la pantalla, el login de vendedor2 muestra "Hay 1 venta sin enviar de Vendedor Uno" y sigue', async () => {
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(90), nombre: 'Vendedor Dos' } })
    const u = userEvent.setup()
    render(
      <SesionRuta>
        <p>Inicio de prueba</p>
      </SesionRuta>,
    )

    await u.type(await screen.findByLabelText(/organización/i), 'demo')
    await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor2')
    await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
    await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))

    expect(
      await screen.findByText('Hay 1 venta sin enviar de Vendedor Uno. Queda guardada en el teléfono.'),
    ).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(1)

    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(await screen.findByLabelText(/repetí el PIN/i)).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(1)
  })
})
