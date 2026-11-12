import 'fake-indexeddb/auto'

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Decimal from 'decimal.js'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../utils/bootstrapDePrueba'

import type { components } from '../../../../src/api/schema.gen'
import { leerSaldoConsiderado } from '../../../../src/areas/ruta/datos/disponibles'
import { RutaScreen } from '../../../../src/areas/ruta/RutaScreen'
import { limpiarAccessToken } from '../../../../src/lib/auth/tokenStore'
import { baseLocal } from '../../../../src/lib/dispositivo/db'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 23, tarea 13.1 (de punta a punta: `fake-indexeddb`, Web Crypto real y un `fetch`
 * simulado; cita COB-04, CRE-08, INV-06, INV-08, SYN-03): Kiosco La Esquina debe $150.000 con
 * límite $200.000; cobranza de $50.000 sin red (saldo y disponible $100.000, «Sin enviar»); venta
 * al mismo cliente sin red; vuelve la señal y se envían en orden (secuencias 1 y 2); «Actualizar
 * datos» trae el saldo con la cobranza y la venta y la marca: no cuenta dos veces; una segunda
 * cobranza vuelve rechazada y deja de contar; «Sincronizar» otra vez no cambia nada.
 */
const PIN_DISPOSITIVO = '482915'
const SALDO_INICIAL = '150000.00'
const CLIENTE = ID(101)

function bootstrapDelFlujo(saldo: string, secuenciaProcesada: number | null): Bootstrap {
  const b = bootstrapDePrueba({ clientes: [clienteDePrueba(1, 'Kiosco La Esquina')] })
  b.sesion.permisos = ['VENDER', 'ABRIR_JORNADA', 'REGISTRAR_COBRANZA']
  const cliente = b.clientes[0]
  if (cliente) {
    cliente.saldo = saldo
    cliente.credito = { limite: '200000.00', politica: 'AUTORIZAR', tolerancia_tipo: 'IMPORTE', tolerancia_valor: '100.00' }
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
  b.sesion.secuencia_procesada = secuenciaProcesada
  return b
}

interface Item {
  operation_id: string
  secuencia: number
  tipo: string
  contenido: { importe?: string }
}

interface Servidor {
  saldo: string
  totalDeLaVenta: string
  secuenciaProcesada: number | null
  conRed: boolean
  rechazarCobranzas: boolean
  lotes: Item[][]
}

function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

function instalarServidor(): Servidor {
  const servidor: Servidor = {
    saldo: SALDO_INICIAL,
    totalDeLaVenta: '0.00',
    secuenciaProcesada: null,
    conRed: true,
    rechazarCobranzas: false,
    lotes: [],
  }
  let jornadaAbierta = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      if (!servidor.conRed) throw new TypeError('Failed to fetch')
      const url = new URL(String(entrada), 'http://x')
      const metodo = (init?.method ?? 'GET').toUpperCase()
      const ruta = url.pathname.replace('/api/v1', '')
      if (ruta === '/auth/login') return respuesta(200, { access_token: 'token-1' })
      if (ruta === '/auth/refresh') return respuesta(200, { access_token: 'token-2' })
      if (ruta === '/yo') return respuesta(200, { usuario: { id: ID(1), nombre: 'Vendedor Uno' } })
      if (ruta === '/stock/jornadas/actual') {
        return jornadaAbierta
          ? respuesta(200, { id: ID(2), estado: 'ABIERTA' })
          : respuesta(404, { codigo: 'JORNADA_INEXISTENTE', title: 'Sin jornada' })
      }
      if (ruta === `/stock/jornadas/${ID(2)}`) return respuesta(200, { id: ID(2), estado: 'ABIERTA' })
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
        return respuesta(200, bootstrapDelFlujo(servidor.saldo, servidor.secuenciaProcesada))
      }
      if (ruta === '/sync/comandos' && metodo === 'POST') {
        const items = (JSON.parse(String(init?.body)) as { items: Item[] }).items
        servidor.lotes.push(items)
        const resultados = items.map((i) => {
          if (i.tipo === 'COBRANZA_REGISTRAR' && servidor.rechazarCobranzas) {
            return { operation_id: i.operation_id, estado: 'RECHAZADO', resultado: null, error_codigo: 'RECURSO_NO_ENCONTRADO', observaciones: [] }
          }
          if (i.tipo === 'COBRANZA_REGISTRAR') {
            servidor.saldo = new Decimal(servidor.saldo).minus(i.contenido.importe ?? '0').toFixed(2)
          } else {
            servidor.saldo = new Decimal(servidor.saldo).plus(servidor.totalDeLaVenta).toFixed(2)
          }
          return { operation_id: i.operation_id, estado: 'ACEPTADO', resultado: null, error_codigo: null, observaciones: [] }
        })
        servidor.secuenciaProcesada = Math.max(...items.map((i) => i.secuencia))
        return respuesta(200, { resultados })
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

async function irA(u: Usuario, nombre: string) {
  await u.click((await screen.findAllByRole('link', { name: nombre }))[0] as HTMLElement)
}

async function cobrar(u: Usuario, importe: string) {
  await irA(u, 'Inicio')
  await u.click(await screen.findByRole('link', { name: 'Cobrar' }))
  await u.click(await screen.findByRole('button', { name: /Kiosco La Esquina/ }))
  await escribir(u, 'Importe a cobrar', importe)
  await u.selectOptions(await screen.findByLabelText('Medio de cobro 1'), 'Efectivo')
  await escribir(u, 'Importe del medio 1', importe)
  await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))
  await u.click(await screen.findByRole('button', { name: 'Registrar' }))
  expect(await screen.findByRole('heading', { name: 'Cobranza guardada' })).toBeInTheDocument()
}

describe('Flujo de cobranza sin conexión de punta a punta (tarea 13.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    limpiarAccessToken()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('cobra $50.000 sin red (100.000), vende al mismo cliente, se envían en orden, el bootstrap no cuenta dos veces y una cobranza rechazada deja de contar (COB-04, CRE-08, INV-06, INV-08, SYN-03)', async () => {
    const servidor = instalarServidor()
    conectado(servidor, true)
    const u = userEvent.setup()
    render(
      <RouterProvider router={createMemoryRouter([{ path: '/ruta/*', element: <RutaScreen /> }], { initialEntries: ['/ruta'] })} />,
    )

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
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('150000.00')

    // Sin red: cobranza de $50.000 (saldo y disponible $100.000), «Sin enviar».
    conectado(servidor, false)
    await cobrar(u, '50000.00')
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()
    expect(await leerSaldoConsiderado(CLIENTE)).toBe('100000.00')
    await irA(u, 'Clientes')
    await u.click(await screen.findByRole('link', { name: /Kiosco La Esquina/ }))
    expect(await screen.findAllByText('$ 100.000,00')).toHaveLength(2) // saldo y disponible
    expect(servidor.lotes).toHaveLength(0)

    // Sin red: venta al mismo cliente; el saldo suma lo vendido.
    await irA(u, 'Inicio')
    await irA(u, 'Vender')
    await u.click(await screen.findByRole('button', { name: /Kiosco La Esquina/ }))
    await u.click(await screen.findByRole('button', { name: 'Agregar Vino A' }))
    await escribir(u, 'Cajas de Vino A', '2')
    await u.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText(/paso 3 de 3/i)
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await screen.findByRole('heading', { name: /Venta 0001-/ })
    const venta = (await baseLocal.ventas.toArray())[0]
    servidor.totalDeLaVenta = venta?.calculo.total ?? '0.00'
    expect(new Decimal(servidor.totalDeLaVenta).gt(0)).toBe(true)
    const esperado = new Decimal('100000.00').plus(servidor.totalDeLaVenta).toFixed(2)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(esperado)

    // Vuelve la señal: se envían la cobranza y la venta, en orden de secuencia.
    conectado(servidor, true)
    await waitFor(() => expect(servidor.lotes).toHaveLength(1))
    expect(servidor.lotes[0]?.map((i) => [i.secuencia, i.tipo])).toEqual([
      [1, 'COBRANZA_REGISTRAR'],
      [2, 'VENTA_CONFIRMAR'],
    ])
    await waitFor(async () => expect((await baseLocal.cola.toArray()).map((c) => c.estado)).toEqual(['ACEPTADO', 'ACEPTADO']))
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(esperado)

    // «Actualizar datos»: el servidor ya tiene las dos y la marca 2; no se cuentan dos veces.
    await irA(u, 'Inicio')
    await u.click(await screen.findByRole('button', { name: 'Actualizar datos' }))
    await waitFor(async () => expect((await baseLocal.sesion.get('actual'))?.secuencia_procesada).toBe(2))
    expect(servidor.saldo).toBe(esperado)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(esperado)

    // Una segunda cobranza sin red cuenta; al volver rechazada, deja de contar.
    conectado(servidor, false)
    await cobrar(u, '20000.00')
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(new Decimal(esperado).minus('20000.00').toFixed(2))
    servidor.rechazarCobranzas = true
    conectado(servidor, true)
    await waitFor(() => expect(servidor.lotes).toHaveLength(2))
    await waitFor(async () => {
      const estados = (await baseLocal.cobranzas.toArray()).filter((c) => c.origen === 'INDEPENDIENTE').map((c) => c.estado_envio)
      expect(estados).toContain('RECHAZADA')
    })
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(esperado)

    // «Sincronizar» otra vez no envía ni cambia nada (INV-06).
    await irA(u, 'Inicio')
    await u.click((await screen.findAllByRole('link', { name: /Sincronización|enviar|Todo enviado|problema|rechaz/i }))[0] as HTMLElement)
    await u.click(await screen.findByRole('button', { name: 'Sincronizar' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled())
    expect(servidor.lotes).toHaveLength(2)
    expect(await leerSaldoConsiderado(CLIENTE)).toBe(esperado)
  }, 240_000)
})
