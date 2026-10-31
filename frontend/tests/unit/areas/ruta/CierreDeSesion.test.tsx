import 'fake-indexeddb/auto'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../../unit/utils/bootstrapDePrueba'

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), obtenerYo: vi.fn() }))

vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: mocks.apiFetch }))
vi.mock('../../../../src/features/identidad/api', () => ({ obtenerYo: mocks.obtenerYo }))

import { CerrarSesionBoton } from '../../../../src/areas/ruta/sesion/CerrarSesionBoton'
import { registrarUsuarioTrasLogin } from '../../../../src/areas/ruta/sesion/arranque'
import { fijarAccessToken, obtenerAccessToken } from '../../../../src/lib/auth/tokenStore'
import { baseLocal, TABLAS_MAESTRAS } from '../../../../src/lib/dispositivo/db'
import { definirPin } from '../../../../src/lib/sesionLocal/pin'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

function respuesta(status: number) {
  return { ok: status >= 200 && status < 300, status, json: async () => ({}) }
}

/** Deja la base como la de `vendedor`: datos maestros, PIN y una operación pendiente simulada. */
async function sembrarSesionDeVendedor() {
  await aplicarBootstrap(bootstrapDePrueba({ clientes: [clienteDePrueba(1, 'Almacén Norte')] }))
  await baseLocal.meta.bulkPut([
    { clave: 'usuario_local_id', valor: ID(1) },
    { clave: 'dispositivo_id', valor: 'disp-1' },
    // Marca de las operaciones pendientes (cola del change 22a): nunca debe borrarse.
    { clave: 'cola_pendiente', valor: 'venta-1' },
  ])
  await definirPin('482915', '482915')
}

async function tablasMaestrasVacias(): Promise<boolean> {
  const cuentas = await Promise.all(TABLAS_MAESTRAS.map((nombre) => baseLocal.table(nombre).count()))
  return cuentas.every((n) => n === 0)
}

/**
 * Change 21, tarea 10.1 (spec `identidad/sesion-local`, "Cerrar sesión y cambiar de usuario en el
 * dispositivo"; `design.md` D16; `02` §12.3; ADR-017): una sola sesión local por dispositivo;
 * cerrar sesión o entrar con otro usuario borra sesión, PIN y datos maestros, nunca las
 * operaciones pendientes ni el `dispositivo_id`.
 */
describe('Cerrar sesión (tarea 10.1)', () => {
  beforeEach(async () => {
    mocks.apiFetch.mockReset()
    mocks.obtenerYo.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('con conexión llama POST /auth/logout y borra sesión, PIN y datos maestros (no el dispositivo ni lo pendiente)', async () => {
    await sembrarSesionDeVendedor()
    fijarAccessToken('tok')
    mocks.apiFetch.mockResolvedValue(respuesta(204))
    const onCerrada = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={onCerrada} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    await u.click(await screen.findByRole('button', { name: /^confirmar$/i }))

    await waitFor(() => expect(onCerrada).toHaveBeenCalledTimes(1))
    const [ruta, init] = mocks.apiFetch.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe('/auth/logout')
    expect(init.method).toBe('POST')
    expect(await tablasMaestrasVacias()).toBe(true)
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
    expect(await baseLocal.meta.get('usuario_local_id')).toBeUndefined()
    expect(await baseLocal.meta.get('fecha_bootstrap')).toBeUndefined()
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-1')
    expect((await baseLocal.meta.get('cola_pendiente'))?.valor).toBe('venta-1')
    expect(obtenerAccessToken()).toBeNull()
  })

  it('no borra nada hasta que se confirma', async () => {
    await sembrarSesionDeVendedor()
    const onCerrada = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={onCerrada} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))

    expect(mocks.apiFetch).not.toHaveBeenCalled()
    expect(await baseLocal.clientes.count()).toBe(1)
    expect(onCerrada).not.toHaveBeenCalled()
  })

  it('sin conexión está deshabilitado y dice que requiere conexión', async () => {
    conectado(false)
    await sembrarSesionDeVendedor()
    render(<CerrarSesionBoton onCerrada={vi.fn()} />)

    expect(screen.getByRole('button', { name: /cerrar sesión/i })).toBeDisabled()
    expect(screen.getByText(/requiere conexión/i)).toBeInTheDocument()
    expect(mocks.apiFetch).not.toHaveBeenCalled()
  })

  it('si el servidor falla no borra nada y lo explica', async () => {
    await sembrarSesionDeVendedor()
    mocks.apiFetch.mockResolvedValue(respuesta(500))
    const onCerrada = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={onCerrada} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    await u.click(await screen.findByRole('button', { name: /^confirmar$/i }))

    expect(await screen.findByText(/no se pudo cerrar la sesión/i)).toBeInTheDocument()
    expect(onCerrada).not.toHaveBeenCalled()
    expect(await baseLocal.clientes.count()).toBe(1)
    expect(await baseLocal.meta.get('pin_hash')).toBeDefined()
  })

  it('un corte de red durante el cierre no borra nada', async () => {
    await sembrarSesionDeVendedor()
    mocks.apiFetch.mockRejectedValue(new TypeError('Failed to fetch'))
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    await u.click(await screen.findByRole('button', { name: /^confirmar$/i }))

    expect(await screen.findByText(/requiere conexión/i)).toBeInTheDocument()
    expect(await baseLocal.clientes.count()).toBe(1)
  })

  it('si el servidor ya no reconoce la sesión (401) igual borra la sesión local', async () => {
    await sembrarSesionDeVendedor()
    mocks.apiFetch.mockResolvedValue(respuesta(401))
    const onCerrada = vi.fn()
    const u = userEvent.setup()
    render(<CerrarSesionBoton onCerrada={onCerrada} />)

    await u.click(screen.getByRole('button', { name: /cerrar sesión/i }))
    await u.click(await screen.findByRole('button', { name: /^confirmar$/i }))

    await waitFor(() => expect(onCerrada).toHaveBeenCalled())
    expect(await tablasMaestrasVacias()).toBe(true)
  })
})

describe('Cambio de usuario en el dispositivo (tarea 10.1, D16)', () => {
  beforeEach(async () => {
    mocks.obtenerYo.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('el login de otro usuario borra sesión, PIN y datos maestros del anterior, conservando lo pendiente', async () => {
    await sembrarSesionDeVendedor()
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(50), nombre: 'Vendedor Dos' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r).toEqual({ cambioDeUsuario: true, hayPin: false })
    expect(await tablasMaestrasVacias()).toBe(true)
    expect(await baseLocal.meta.get('pin_hash')).toBeUndefined()
    expect((await baseLocal.meta.get('usuario_local_id'))?.valor).toBe(ID(50))
    expect((await baseLocal.meta.get('dispositivo_id'))?.valor).toBe('disp-1')
    expect((await baseLocal.meta.get('cola_pendiente'))?.valor).toBe('venta-1')
  })

  it('el login del mismo usuario no borra nada y conserva su PIN', async () => {
    await sembrarSesionDeVendedor()
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r).toEqual({ cambioDeUsuario: false, hayPin: true })
    expect(await baseLocal.clientes.count()).toBe(1)
  })

  it('un dispositivo sin sesión local registra al usuario y pide definir el PIN', async () => {
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r).toEqual({ cambioDeUsuario: false, hayPin: false })
    expect((await baseLocal.meta.get('usuario_local_id'))?.valor).toBe(ID(1))
  })

  it('tras un bloqueo por intentos, el mismo usuario conserva los datos y debe definir un PIN nuevo', async () => {
    await sembrarSesionDeVendedor()
    await baseLocal.meta.bulkDelete(['pin_hash', 'pin_sal', 'pin_iteraciones', 'pin_intentos'])
    mocks.obtenerYo.mockResolvedValue({ usuario: { id: ID(1), nombre: 'Vendedor Uno' } })

    const r = await registrarUsuarioTrasLogin()

    expect(r).toEqual({ cambioDeUsuario: false, hayPin: false })
    expect(await baseLocal.clientes.count()).toBe(1)
  })
})
