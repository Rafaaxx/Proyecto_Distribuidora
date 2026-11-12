import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ generarPdfDeNota: vi.fn(), compartir: vi.fn() }))
// El PDF real (pdfmake) no corre en jsdom; el resto del flujo no tiene ningún mock de módulos propios.
vi.mock('../../../../src/lib/nota/pdf', () => ({ generarPdfDeNota: mocks.generarPdfDeNota }))

import { clienteDePrueba, bootstrapDePrueba, ID } from '../../utils/bootstrapDePrueba'

import type { components } from '../../../../src/api/schema.gen'
import { RutaScreen } from '../../../../src/areas/ruta/RutaScreen'
import { limpiarAccessToken } from '../../../../src/lib/auth/tokenStore'
import { baseLocal } from '../../../../src/lib/dispositivo/db'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 22a, tarea 17.1 (de punta a punta: `fake-indexeddb`, Web Crypto real y un `fetch`
 * simulado; cita INV-01, CRE-08, SEG-05, SYN-01, VTA-13, `00` §9 criterios 5 a 7): login, PIN,
 * jornada, bootstrap; sin red, la venta del criterio 5; una segunda venta al mismo cliente que
 * excede el crédito y se resuelve con el PIN de `sup01` (criterio 6); la nota compartida
 * (criterio 7); "2 ventas sin enviar"; "Actualizar datos" con red no las toca; la cola tiene dos
 * sobres en orden con la forma del fixture de contrato.
 */
const aqui = dirname(fileURLToPath(import.meta.url))
const COMPARTIDO = join(aqui, '..', '..', '..', '..', '..', 'shared', 'fixtures')
const VECTOR = JSON.parse(readFileSync(join(COMPARTIDO, 'pin', 'derivacion.json'), 'utf-8')) as {
  casos: { id: string; pin: string; sal_hex: string; iteraciones: number; hash_hex: string }[]
}
const PIN_SUP = VECTOR.casos.find((c) => c.id === 'PIN-DERIV-03') as (typeof VECTOR.casos)[number]
const CONTRATO = JSON.parse(readFileSync(join(COMPARTIDO, 'sync', 'venta-confirmar-offline.json'), 'utf-8')) as {
  sobre: { contenido: Record<string, unknown> } & Record<string, unknown>
}
const PIN_DISPOSITIVO = '482915'
const SUP01 = ID(60)
const TRANSFERENCIA = ID(23)

function bootstrapDelFlujo(): Bootstrap {
  const b = bootstrapDePrueba({ clientes: [clienteDePrueba(1, 'Almacén Uno')] })
  b.sesion.permisos = ['VENDER', 'ABRIR_JORNADA']
  const cliente = b.clientes[0]
  if (cliente) {
    cliente.saldo = '0.00'
    cliente.credito = { limite: '30000.00', politica: 'AUTORIZAR', tolerancia_tipo: 'IMPORTE', tolerancia_valor: '100.00' }
  }
  b.productos = [
    {
      id: ID(30),
      codigo: 'V1',
      nombre: 'Vino A',
      categoria_id: ID(40),
      marca_id: null,
      alicuota_id: ID(22),
      alicuota_valor: '0.210000',
      presentacion_referencia_id: ID(31),
      presentaciones: [
        { id: ID(31), nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
        { id: ID(32), nombre: 'Botella', unidades_base: 1, es_referencia: false },
      ],
    },
  ]
  const version = b.listas[0]?.versiones[0]
  if (version) version.precios = [{ producto_id: ID(30), precio_referencia: '12500.00', unidades_referencia: 6 }]
  b.stock = [{ producto_id: ID(30), cantidad_base: 63 }]
  b.catalogos.medios_pago = [
    { id: ID(20), nombre: 'Efectivo', requiere_referencia: false },
    { id: TRANSFERENCIA, nombre: 'Transferencia', requiere_referencia: true },
  ]
  b.contexto_venta = {
    descuento_manual: { habilitado: true, motivo_obligatorio: false, tiene_permiso: true, tope: '0.100000', puede_autorizar: false },
    puede_superar_credito: false,
  }
  b.autorizadores = [
    {
      id: SUP01,
      nombre: 'sup01',
      permisos: ['SUPERAR_CREDITO'],
      pin_hash: PIN_SUP.hash_hex,
      pin_sal: PIN_SUP.sal_hex,
      iteraciones: PIN_SUP.iteraciones,
    },
  ]
  return b
}

interface Servidor {
  conRed: boolean
  llamadas: string[]
}

function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

function instalarServidor(): Servidor {
  const servidor: Servidor = { conRed: true, llamadas: [] }
  let jornadaAbierta = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      if (!servidor.conRed) throw new TypeError('Failed to fetch')
      const url = new URL(String(entrada), 'http://x')
      const metodo = (init?.method ?? 'GET').toUpperCase()
      servidor.llamadas.push(`${metodo} ${url.pathname}`)
      const ruta = url.pathname.replace('/api/v1', '')
      if (ruta === '/auth/login') return respuesta(200, { access_token: 'token-1' })
      if (ruta === '/auth/refresh') return respuesta(200, { access_token: 'token-2' })
      if (ruta === '/yo') return respuesta(200, { usuario: { id: ID(1), nombre: 'Vendedor Uno' } })
      if (ruta === '/stock/jornadas/actual') {
        return jornadaAbierta
          ? respuesta(200, { id: ID(2), estado: 'ABIERTA' })
          : respuesta(404, { codigo: 'JORNADA_INEXISTENTE', title: 'Sin jornada' })
      }
      if (ruta === '/stock/ubicaciones') {
        return respuesta(200, {
          items: [{ id: ID(3), nombre: 'Camioneta 1', activo: true, requiere_toma: true, jornada: null }],
          cursor_siguiente: null,
        })
      }
      if (ruta === '/stock/jornadas' && metodo === 'POST') {
        jornadaAbierta = true
        return respuesta(201, { id: ID(2), estado: 'ABIERTA' })
      }
      if (ruta === '/sync/bootstrap') {
        if (!jornadaAbierta) return respuesta(409, { codigo: 'JORNADA_REQUERIDA', title: 'Sin jornada' })
        return respuesta(200, bootstrapDelFlujo())
      }
      return respuesta(404, { codigo: 'SIN_REGLA', title: `Sin regla para ${metodo} ${ruta}` })
    }),
  )
  return servidor
}

function conectado(servidor: Servidor, valor: boolean) {
  servidor.conRed = valor
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
  act(() => {
    window.dispatchEvent(new Event(valor ? 'online' : 'offline'))
  })
}

type Usuario = ReturnType<typeof userEvent.setup>

async function escribir(u: Usuario, etiqueta: string | RegExp, texto: string) {
  const campo = await screen.findByLabelText(etiqueta)
  await u.clear(campo)
  await u.type(campo, texto)
}

async function cargarVino(u: Usuario) {
  await u.click(await screen.findByRole('button', { name: 'Agregar Vino A' }))
  await escribir(u, 'Cajas de Vino A', '2')
  await escribir(u, 'Unidades de Vino A', '3')
}

async function irAlCobro(u: Usuario) {
  await u.click(screen.getByRole('button', { name: 'Siguiente' }))
  await screen.findByText(/paso 3 de 3/i)
}

async function cobrar(u: Usuario, indice: number, medio: string, importe: string, referencia?: string) {
  await u.click(screen.getByRole('button', { name: 'Agregar medio de cobro' }))
  await u.selectOptions(screen.getByLabelText(`Medio de cobro ${indice}`), medio)
  await escribir(u, `Importe del medio ${indice}`, importe)
  if (referencia !== undefined) await escribir(u, `Referencia del medio ${indice}`, referencia)
}

async function elegirClienteYCargar(u: Usuario) {
  await u.click(await screen.findByRole('button', { name: /Almacén Uno/ }))
  await cargarVino(u)
}

function claves(objeto: object): string[] {
  return Object.keys(objeto).sort()
}

describe('Flujo de venta de ruta de punta a punta (tarea 17.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    limpiarAccessToken()
    mocks.generarPdfDeNota.mockReset().mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    mocks.compartir.mockReset().mockResolvedValue(undefined)
    Object.defineProperty(window.navigator, 'canShare', { configurable: true, value: () => true })
    Object.defineProperty(window.navigator, 'share', { configurable: true, value: mocks.compartir })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('criterios 5 a 7: venta sin red, segunda venta con PIN de sup01, nota compartida, 2 sin enviar y Actualizar datos que no las toca (INV-01, CRE-08)', async () => {
    const servidor = instalarServidor()
    conectado(servidor, true)
    const u = userEvent.setup()
    render(
      <RouterProvider router={createMemoryRouter([{ path: '/ruta/*', element: <RutaScreen /> }], { initialEntries: ['/ruta'] })} />,
    )

    // Login, PIN del dispositivo, jornada y bootstrap.
    await u.type(await screen.findByLabelText(/organización/i), 'demo')
    await u.type(screen.getByLabelText(/^usuario$/i), 'vendedor')
    await u.type(screen.getByLabelText(/contraseña/i), 'secreta1')
    await u.click(screen.getByRole('button', { name: /iniciar sesión/i }))
    await escribir(u, /^PIN$/i, PIN_DISPOSITIVO)
    await escribir(u, /repetí el PIN/i, PIN_DISPOSITIVO)
    await u.click(screen.getByRole('button', { name: /guardar PIN/i }))
    await u.click(await screen.findByRole('link', { name: /abrir jornada/i }))
    await screen.findByRole('option', { name: 'Camioneta 1' })
    await u.selectOptions(screen.getByLabelText('Ubicación'), ID(3))
    await u.click(screen.getByRole('button', { name: 'Abrir jornada' }))
    expect(await screen.findByText(/Hola, Vendedor Uno/)).toBeInTheDocument()
    expect(await screen.findByText('Todo enviado')).toBeInTheDocument()

    // Sin red: criterio 5 (2 cajas + 3 botellas, 5 % general, efectivo y transferencia).
    conectado(servidor, false)
    const llamadasSinRed = servidor.llamadas.length
    await u.click(screen.getAllByRole('link', { name: 'Vender' })[0] as HTMLElement)
    await elegirClienteYCargar(u)
    await escribir(u, 'Descuento general (%)', '5')
    await waitFor(() => expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 29.687,50'))
    await irAlCobro(u)
    await cobrar(u, 1, ID(20), '10000')
    await cobrar(u, 2, TRANSFERENCIA, '10000', 'TRF-0001')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()

    // Criterio 6: la segunda venta al mismo cliente excede el crédito y se resuelve con el PIN de sup01.
    await u.click(screen.getByRole('link', { name: 'Nueva venta' }))
    await elegirClienteYCargar(u)
    await irAlCobro(u)
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    const dialogo = await screen.findByRole('dialog', { name: 'PIN del supervisor' })
    await u.type(within(dialogo).getByLabelText('PIN de sup01'), PIN_SUP.pin)
    await u.click(within(dialogo).getByRole('button', { name: 'Verificar y confirmar' }))
    expect(await screen.findByRole('heading', { name: 'Venta 0001-000009' })).toBeInTheDocument()

    // Criterio 7: la nota se comparte sin señal.
    await u.click(screen.getByRole('button', { name: 'Compartir nota' }))
    await waitFor(() => expect(mocks.compartir).toHaveBeenCalledTimes(1))
    const compartido = mocks.compartir.mock.calls[0]?.[0] as { files: File[] }
    expect(compartido.files[0]?.name).toBe('nota-de-venta-0001-000009.pdf')

    // El inicio cuenta las dos ventas sin enviar; nada tocó la red.
    await u.click(screen.getAllByRole('link', { name: 'Inicio' })[0] as HTMLElement)
    expect(await screen.findByText('2 ventas sin enviar')).toBeInTheDocument()
    expect(servidor.llamadas.length).toBe(llamadasSinRed)

    // Con red, "Actualizar datos" baja un bootstrap nuevo y no toca las ventas ni la cola (INV-01).
    conectado(servidor, true)
    await u.click(await screen.findByRole('button', { name: 'Actualizar datos' }))
    await waitFor(() => expect(servidor.llamadas.filter((l) => l === 'GET /api/v1/sync/bootstrap').length).toBeGreaterThan(1))
    expect(await screen.findByText('2 ventas sin enviar')).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(2)
    expect(servidor.llamadas.some((l) => l.startsWith('POST') && l.includes('/ventas'))).toBe(false)

    // La cola: dos sobres en orden, con la forma del fixture de contrato y sin PIN ni credenciales.
    const cola = (await baseLocal.cola.toArray()).sort((a, b) => a.sobre.secuencia - b.sobre.secuencia)
    expect(cola).toHaveLength(2)
    const [primero, segundo] = cola.map((c) => c.sobre)
    expect(segundo?.secuencia).toBe((primero?.secuencia ?? 0) + 1)
    for (const sobre of [primero, segundo]) {
      expect(sobre).toBeDefined()
      if (!sobre) continue
      expect(claves(sobre)).toEqual(claves(CONTRATO.sobre))
      // Además de las claves del fixture, el 5 % manual de este flujo agrega las del descuento manual.
      expect(claves(sobre.contenido)).toEqual(expect.arrayContaining(claves(CONTRATO.sobre.contenido)))
      expect(sobre.tipo).toBe('VENTA_CONFIRMAR')
      expect(sobre.modo).toBe('OFFLINE')
      expect(sobre.version).toBe(1)
      expect(JSON.stringify(sobre)).not.toContain(PIN_SUP.pin)
    }
    expect(primero?.contenido.credito).toMatchObject({ resolucion: 'SIN_EXCESO' })
    expect(segundo?.contenido.credito).toMatchObject({ resolucion: 'PIN_SUPERVISOR', autorizador_id: SUP01 })
  }, 240_000)
})
