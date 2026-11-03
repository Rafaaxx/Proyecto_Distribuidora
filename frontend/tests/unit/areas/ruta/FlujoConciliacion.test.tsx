import 'fake-indexeddb/auto'

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../utils/bootstrapDePrueba'

import type { components } from '../../../../src/api/schema.gen'
import { RutaScreen } from '../../../../src/areas/ruta/RutaScreen'
import { limpiarAccessToken } from '../../../../src/lib/auth/tokenStore'
import { LEYENDA_INCLUYE_VENTAS } from '../../../../src/domain/ruta/lecturasLocales'
import { baseLocal } from '../../../../src/lib/dispositivo/db'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 22c, tarea 11.1 (de punta a punta: `fake-indexeddb`, Web Crypto real y un `fetch`
 * simulado; cita CRE-08, RUT-04, INV-06, SYN-07): bootstrap con 63 botellas; venta de 15 sin red
 * (Stock muestra 48 con la leyenda); vuelve la señal y se envía con `STOCK_NEGATIVO`; «Actualizar
 * datos» con 48 y la marca de secuencia procesada: Stock sigue en 48 y sin leyenda; «Sincronización»
 * y el detalle muestran la observación traducida; «Sincronizar» otra vez no cambia nada.
 */
const PIN_DISPOSITIVO = '482915'

function bootstrapDelFlujo(stock: number, secuenciaProcesada: number | null): Bootstrap {
  const b = bootstrapDePrueba({ clientes: [clienteDePrueba(1, 'Almacén Uno')] })
  b.sesion.permisos = ['VENDER', 'ABRIR_JORNADA']
  const cliente = b.clientes[0]
  if (cliente) {
    cliente.saldo = '0.00'
    cliente.credito = { limite: '500000.00', politica: 'AUTORIZAR', tolerancia_tipo: 'IMPORTE', tolerancia_valor: '100.00' }
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
  b.stock = [{ producto_id: ID(30), cantidad_base: stock }]
  b.sesion.secuencia_procesada = secuenciaProcesada
  return b
}

interface Servidor {
  stock: number
  secuenciaProcesada: number | null
  conRed: boolean
  llamadas: string[]
  lotes: { operation_id: string; secuencia: number }[][]
}

function respuesta(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

function instalarServidor(): Servidor {
  const servidor: Servidor = { stock: 63, secuenciaProcesada: null, conRed: true, llamadas: [], lotes: [] }
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
        return respuesta(200, bootstrapDelFlujo(servidor.stock, servidor.secuenciaProcesada))
      }
      if (ruta === '/sync/comandos' && metodo === 'POST') {
        const items = (JSON.parse(String(init?.body)) as { items: { operation_id: string; secuencia: number }[] }).items
        servidor.lotes.push(items)
        // La venta de 15 botellas deja el stock del servidor en 48 y lo anota como negativo (SYN-07).
        servidor.stock = 48
        servidor.secuenciaProcesada = Math.max(...items.map((i) => i.secuencia))
        return respuesta(200, {
          resultados: items.map((i) => ({
            operation_id: i.operation_id,
            estado: 'ACEPTADO_CON_OBSERVACIONES',
            resultado: null,
            error_codigo: null,
            observaciones: [
              { codigo: 'STOCK_NEGATIVO', operacion_tipo: 'VENTA', operacion_id: i.operation_id, detalle: { producto_id: ID(30) } },
            ],
          })),
        })
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

async function venderYConfirmar(u: Usuario) {
  await u.click(await screen.findByRole('button', { name: /Almacén Uno/ }))
  await u.click(await screen.findByRole('button', { name: 'Agregar Vino A' }))
  await escribir(u, 'Cajas de Vino A', '2')
  await escribir(u, 'Unidades de Vino A', '3')
  await u.click(screen.getByRole('button', { name: 'Siguiente' }))
  await screen.findByText(/paso 3 de 3/i)
  await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
}

describe('Flujo de conciliación local de punta a punta (tarea 11.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    limpiarAccessToken()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('63 botellas, venta de 15 sin red, envío con STOCK_NEGATIVO y bootstrap: 48 una sola vez, observación traducida, sin reenvío (CRE-08, RUT-04, INV-06, SYN-07)', async () => {
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

    // Sin red: una venta de 2 cajas y 3 unidades (15 botellas). Stock local = 63 - 15 = 48 con la leyenda.
    conectado(servidor, false)
    await u.click(screen.getAllByRole('link', { name: 'Vender' })[0] as HTMLElement)
    await venderYConfirmar(u)
    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    await u.click(screen.getAllByRole('link', { name: 'Stock' })[0] as HTMLElement)
    expect(await screen.findByText('8 cajas')).toBeInTheDocument()
    expect(screen.getByText(LEYENDA_INCLUYE_VENTAS)).toBeInTheDocument()

    // Vuelve la señal: se envía y el servidor anota STOCK_NEGATIVO; el stock sigue en 48.
    conectado(servidor, true)
    await waitFor(() => expect(servidor.lotes).toHaveLength(1))
    await waitFor(async () => expect((await baseLocal.cola.toArray())[0]?.estado).toBe('ACEPTADO_CON_OBSERVACIONES'))
    expect(screen.getByText('8 cajas')).toBeInTheDocument()

    // «Actualizar datos»: el bootstrap ya trae 48 y la marca; el teléfono no descuenta dos veces.
    await u.click(screen.getAllByRole('link', { name: 'Inicio' })[0] as HTMLElement)
    await u.click(await screen.findByRole('button', { name: 'Actualizar datos' }))
    await waitFor(async () => expect((await baseLocal.sesion.get('actual'))?.secuencia_procesada).toBe(1))
    await u.click(screen.getAllByRole('link', { name: 'Stock' })[0] as HTMLElement)
    expect(await screen.findByText('8 cajas')).toBeInTheDocument()
    expect(screen.queryByText(LEYENDA_INCLUYE_VENTAS)).not.toBeInTheDocument()

    // «Sincronización» y el detalle de la venta muestran la observación traducida.
    await u.click(screen.getByRole('link', { name: 'Todo enviado' }))
    expect(await screen.findByText('Quedó stock negativo de Vino A.')).toBeInTheDocument()
    await u.click(await screen.findByRole('link', { name: /0001-000008/ }))
    expect(await screen.findByText('Quedó stock negativo de Vino A.')).toBeInTheDocument()

    // «Sincronizar» otra vez no envía ni cambia nada (INV-06).
    await u.click(screen.getByRole('link', { name: 'Todo enviado' }))
    await u.click(await screen.findByRole('button', { name: 'Sincronizar' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled())
    expect(servidor.lotes).toHaveLength(1)
    expect((await baseLocal.cola.toArray())[0]?.estado).toBe('ACEPTADO_CON_OBSERVACIONES')
  }, 240_000)
})
