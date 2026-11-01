import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { components } from '../../../../../src/api/schema.gen'

const mocks = vi.hoisted(() => ({ confirmar: vi.fn(), verificar: vi.fn(), fetch: vi.fn(), dispararTrasVenta: vi.fn() }))
vi.mock('../../../../../src/sync/disparadores', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../../src/sync/disparadores')>()
  return { ...real, dispararTrasVenta: mocks.dispararTrasVenta }
})
vi.mock('../../../../../src/sync/confirmarVentaLocal', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../../src/sync/confirmarVentaLocal')>()
  mocks.confirmar.mockImplementation(real.confirmarVentaLocal)
  return { ...real, confirmarVentaLocal: mocks.confirmar }
})
vi.mock('../../../../../src/lib/sesionLocal/pinSupervisor', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../../src/lib/sesionLocal/pinSupervisor')>()
  mocks.verificar.mockImplementation(real.verificarPinDeSupervisor)
  return { ...real, verificarPinDeSupervisor: mocks.verificar }
})

import { useGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/contextoGuarda'
import { ProveedorGuardaDelCarrito } from '../../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { VenderScreen } from '../../../../../src/areas/ruta/ventas/VenderScreen'
import { VentaGuardadaScreen } from '../../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { FALTA_CONTADO_DE_CONSUMIDOR_FINAL } from '../../../../../src/domain/ventas/calculoDeVenta'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { ID } from '../../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { montarEnRuta } from '../../../utils/rutaDePrueba'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 22a, tareas 10.1 y 10.2 (spec `ventas/venta-en-ruta`; `design.md` D1, D6 a D10, D14;
 * cita SYN-01, PRC-22, DSC-05, DSC-06, CLI-03, STK-06, CRE-04 a CRE-07, SEG-05): la venta de ruta
 * en tres pasos (Cliente, Pedido, Cobro y confirmación) sobre la base local, con o sin señal.
 */
const aqui = dirname(fileURLToPath(import.meta.url))
const VECTOR = JSON.parse(
  readFileSync(join(aqui, '..', '..', '..', '..', '..', '..', 'shared', 'fixtures', 'pin', 'derivacion.json'), 'utf-8'),
) as { casos: { id: string; pin: string; sal_hex: string; iteraciones: number; hash_hex: string }[] }
const PIN_SUP = VECTOR.casos.find((c) => c.id === 'PIN-DERIV-03') as (typeof VECTOR.casos)[number]
const SUP01 = ID(60)
const TRANSFERENCIA = ID(23)

/** Vino A: caja x6 a $12.500 la caja (PRC-22); 2 cajas + 3 botellas = 15 botellas = $31.250,00. */
function bootstrapDeVino(cambios: (b: Bootstrap) => void = () => undefined): Bootstrap {
  return bootstrapParaVender((b) => {
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
    cambios(b)
  })
}

function conCliente(cambio: (c: Bootstrap['clientes'][number]) => void): (b: Bootstrap) => void {
  return (b) => {
    const c = b.clientes[0]
    if (c) cambio(c)
  }
}

function montar(ruta = '/ruta/vender') {
  const vista = montarEnRuta(
    <ProveedorGuardaDelCarrito>
      <Sonda />
      <Routes>
        <Route path="/ruta/vender" element={<VenderScreen />} />
        <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
      </Routes>
    </ProveedorGuardaDelCarrito>,
    { ruta },
  )
  return { ...vista, u: userEvent.setup() }
}

function Sonda() {
  const { ocupado } = useGuardaDelCarrito()
  return <p data-testid="guarda">{ocupado ? 'carrito abierto' : 'sin carrito'}</p>
}

type Usuario = ReturnType<typeof userEvent.setup>

async function elegirCliente(u: Usuario, nombre = 'Almacén Uno') {
  await u.click(await screen.findByRole('button', { name: new RegExp(nombre) }))
}

async function escribir(u: Usuario, etiqueta: string | RegExp, texto: string) {
  const campo = await screen.findByLabelText(etiqueta)
  await u.clear(campo)
  await u.type(campo, texto)
}

/** Agrega Vino A y carga 2 cajas + 3 botellas. */
async function cargarVino(u: Usuario, cajas = '2', unidades = '3') {
  await u.click(await screen.findByRole('button', { name: 'Agregar Vino A' }))
  await escribir(u, 'Cajas de Vino A', cajas)
  await escribir(u, 'Unidades de Vino A', unidades)
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

function sinSenal() {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
}

describe('VenderScreen: la venta del criterio 5 (tarea 10.1)', () => {
  beforeEach(async () => {
    mocks.confirmar.mockClear()
    mocks.fetch.mockReset()
    vi.stubGlobal('fetch', mocks.fetch)
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDeVino())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('cliente, 2 cajas + 3 botellas, 5 % general, efectivo y transferencia con referencia: se guarda sin llamar a POST /ventas', async () => {
    const { u } = montar()

    // Paso 1: la cartera primero.
    const clientes = await screen.findAllByRole('button', { name: /Almacén Uno|Kiosco Dos/ })
    expect(clientes[0]).toHaveAccessibleName(/Almacén Uno/)
    await elegirCliente(u)

    // Paso 2: el pedido.
    await cargarVino(u)
    expect(screen.getByTestId('guarda')).toHaveTextContent('carrito abierto')
    await waitFor(() => expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 31.250,00'))
    await escribir(u, 'Descuento general (%)', '5')
    await waitFor(() => expect(screen.getByTestId('total-de-la-venta')).toHaveTextContent('$ 29.687,50'))
    await irAlCobro(u)

    // Paso 3: cobro y confirmación.
    await cobrar(u, 1, ID(20), '10000')
    await cobrar(u, 2, TRANSFERENCIA, '10000', 'TRF-0001')
    expect(screen.getByTestId('cobrado')).toHaveTextContent('$ 20.000,00')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    // Venta guardada.
    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()
    expect(screen.getByTestId('guarda')).toHaveTextContent('sin carrito')
    expect(mocks.fetch).not.toHaveBeenCalled()

    const comandos = await baseLocal.cola.toArray()
    expect(comandos).toHaveLength(1)
    expect(comandos[0]?.sobre).toMatchObject({
      tipo: 'VENTA_CONFIRMAR',
      modo: 'OFFLINE',
      usuario_id: ID(1),
      contenido: {
        numero: '0001-000008',
        total: '29687.50',
        descuento_manual_general: '0.050000',
        credito: { resolucion: 'SIN_EXCESO', acepta_exceso: false },
        cobranza: {
          medios: [
            { medio_pago_id: ID(20), importe: '10000.00', referencia: null },
            { medio_pago_id: TRANSFERENCIA, importe: '10000.00', referencia: 'TRF-0001' },
          ],
        },
      },
    })
    expect(JSON.stringify(comandos[0]?.sobre)).not.toMatch(/credenciales|"pin"/i)
    const venta = await baseLocal.ventas.toCollection().first()
    expect(venta?.nota?.saldo_resultante).toBe('11188.00')
  })

  it('después de confirmar dispara la sincronización una vez; si la confirmación falla, no (change 22b, D6)', async () => {
    mocks.dispararTrasVenta.mockClear()
    mocks.confirmar.mockRejectedValueOnce(new Error('falla inyectada'))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '1', '0')
    await irAlCobro(u)

    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(await screen.findByText('No se pudo guardar la venta. Probá de nuevo.')).toBeInTheDocument()
    expect(mocks.dispararTrasVenta).not.toHaveBeenCalled()

    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    expect(mocks.dispararTrasVenta).toHaveBeenCalledTimes(1)
  })

  it('funciona igual sin señal', async () => {
    sinSenal()
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '1', '0')
    await irAlCobro(u)

    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('sin VENDER no hay pantalla de venta', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.sesion.permisos = ['CONSULTAR_STOCK']
      }),
    )
    montar()

    expect(await screen.findByText('No tenés permiso para vender.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Almacén Uno/ })).not.toBeInTheDocument()
  })

  it('una cantidad que no es entera cuenta como cero y no se puede pasar al cobro sin productos', async () => {
    const { u } = montar()
    await elegirCliente(u)
    await u.click(await screen.findByRole('button', { name: 'Agregar Vino A' }))
    await escribir(u, 'Cajas de Vino A', '0')

    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  })

  it('con una lista distinta al cliente sin USAR_LISTA_ANTERIOR no se ofrece elegir lista', async () => {
    const { u } = montar()
    await elegirCliente(u)

    await screen.findByRole('button', { name: 'Agregar Vino A' })
    expect(screen.queryByLabelText('Lista de precios')).not.toBeInTheDocument()
  })

  it('con USAR_LISTA_ANTERIOR y motivo exigido, elegir otra versión sin motivo no deja confirmar', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.sesion.permisos = ['VENDER', 'USAR_LISTA_ANTERIOR']
        b.configuracion.motivo_obligatorio_lista = true
        b.catalogos.motivos = [{ id: ID(21), ambito: 'LISTA_ANTERIOR', nombre: 'Acuerdo' }]
        const lista = b.listas[0]
        const vigente = lista?.versiones[0]
        if (lista && vigente) {
          lista.versiones.push({
            id: ID(52),
            numero: 0,
            estado: 'HISTORICA',
            vigencia_desde: '2026-09-01T00:00:00Z',
            vigencia_hasta: '2026-10-01T00:00:00Z',
            precios: [{ producto_id: ID(30), precio_referencia: '10000.00', unidades_referencia: 6 }],
          })
        }
      }),
    )
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '1', '0')

    await u.selectOptions(await screen.findByLabelText('Versión'), ID(52))
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(screen.getByText('Elegí el motivo para usar otra lista o una versión anterior.')).toBeInTheDocument()
  })

  it('si la transacción falla no se guarda nada y el carrito sigue abierto para reintentar', async () => {
    mocks.confirmar.mockRejectedValueOnce(new Error('falla inyectada'))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '1', '0')
    await irAlCobro(u)

    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByText('No se pudo guardar la venta. Probá de nuevo.')).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(0)
    expect(screen.getByTestId('guarda')).toHaveTextContent('carrito abierto')
    // El reintento usa el mismo operation_id y se guarda una sola venta (INV-06).
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(await baseLocal.ventas.count()).toBe(1)
    expect(await baseLocal.cola.count()).toBe(1)
  })

  it('se puede llegar con el cliente ya elegido desde la ficha (?cliente=) y arranca en el pedido', async () => {
    montar(`/ruta/vender?cliente=${ID(101)}`)

    expect(await screen.findByRole('button', { name: 'Agregar Vino A' })).toBeInTheDocument()
    expect(screen.getByText(/paso 2 de 3/i)).toBeInTheDocument()
  })
})

describe('VenderScreen: las reglas locales (tarea 10.2)', () => {
  beforeEach(async () => {
    mocks.confirmar.mockClear()
    mocks.verificar.mockClear()
    vi.stubGlobal('fetch', mocks.fetch)
    sinSenal()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('consumidor final: con cobro parcial no se confirma; con el total exacto sí y sin panel de crédito (CLI-03)', async () => {
    await aplicarBootstrap(bootstrapDeVino(conCliente((c) => (c.es_consumidor_final = true))))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await irAlCobro(u)
    await cobrar(u, 1, ID(20), '20000')

    expect(screen.getByText(FALTA_CONTADO_DE_CONSUMIDOR_FINAL)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(screen.queryByTestId('panel-de-credito')).not.toBeInTheDocument()

    await escribir(u, 'Importe del medio 1', '31250')
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeEnabled()
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    expect((await baseLocal.cola.toArray())[0]?.sobre.contenido).toMatchObject({ credito: { resolucion: 'SIN_EXCESO' } })
  })

  it('stock sin PERMITIR_STOCK_NEGATIVO: la línea avisa lo que queda y la venta no se confirma (D6 = C)', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.stock = [{ producto_id: ID(30), cantidad_base: 48 }]
      }),
    )
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '0', '50')

    expect(await screen.findByText('Supera el stock del vehículo (quedan 48)')).toBeInTheDocument()
    await irAlCobro(u)
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(
      screen.getByText('No se puede confirmar: actualizá los datos con señal para ver el stock del vehículo.'),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Vender igual')).not.toBeInTheDocument()
  })

  it('stock con PERMITIR_STOCK_NEGATIVO: aviso y "Vender igual"; aceptado se confirma y el disponible queda en -2', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.sesion.permisos = ['VENDER', 'PERMITIR_STOCK_NEGATIVO']
        b.stock = [{ producto_id: ID(30), cantidad_base: 48 }]
      }),
    )
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '0', '50')
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    await u.click(screen.getByLabelText('Vender igual'))
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    const movimientos = await baseLocal.movimientos_locales.filter((m) => m.tipo === 'VENTA_STOCK').toArray()
    expect(48 + movimientos.reduce((suma, m) => suma + (m.cantidad_base ?? 0), 0)).toBe(-2)
  })

  it('con el permiso y sin aceptar "Vender igual" no se confirma nada y el carrito sigue abierto (INV-01)', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.sesion.permisos = ['VENDER', 'PERMITIR_STOCK_NEGATIVO']
        b.stock = [{ producto_id: ID(30), cantidad_base: 48 }]
      }),
    )
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u, '0', '50')
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(await baseLocal.ventas.count()).toBe(0)
    expect(screen.getByTestId('guarda')).toHaveTextContent('carrito abierto')
  })

  const tolerancia = (tipo: 'AUTORIZAR' | 'BLOQUEAR' | 'ADVERTIR', valor: string | null) =>
    conCliente((c) => {
      c.saldo = '0.00'
      c.credito = { limite: '30000.00', politica: tipo, tolerancia_tipo: valor === null ? null : 'IMPORTE', tolerancia_valor: valor }
    })

  it('exceso dentro de la tolerancia: se confirma por TOLERANCIA_OFFLINE sin pedir PIN (CRE-06)', async () => {
    await aplicarBootstrap(bootstrapDeVino(tolerancia('AUTORIZAR', '5000.00')))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await irAlCobro(u)

    expect(screen.getByTestId('panel-de-credito')).toHaveTextContent('se confirma por la tolerancia sin conexión')
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    expect((await baseLocal.cola.toArray())[0]?.sobre.contenido.credito).toMatchObject({
      resolucion: 'TOLERANCIA_OFFLINE',
      acepta_exceso: true,
      saldo_considerado: '0.00',
    })
  })

  it('política BLOQUEAR: no se confirma y se sugiere cobrar más o sacar productos (CRE-07)', async () => {
    await aplicarBootstrap(bootstrapDeVino(tolerancia('BLOQUEAR', null)))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(screen.getByTestId('panel-de-credito')).toHaveTextContent('Aumentá la cobranza o sacá productos')
  })

  it('política ADVERTIR: pide aceptar el exceso y, aceptado, queda ADVERTENCIA_ACEPTADA (CRE-04)', async () => {
    await aplicarBootstrap(bootstrapDeVino(tolerancia('ADVERTIR', null)))
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    await u.click(screen.getByLabelText('Aceptar el exceso de crédito'))
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    expect((await baseLocal.cola.toArray())[0]?.sobre.contenido.credito).toMatchObject({ resolucion: 'ADVERTENCIA_ACEPTADA' })
  })

  describe('fuera de la tolerancia: PIN de un supervisor en el teléfono (SEG-05, D10)', () => {
    const conSupervisor = (b: Bootstrap) => {
      tolerancia('AUTORIZAR', '100.00')(b)
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
    }

    async function hastaElPin(u: Usuario) {
      await elegirCliente(u)
      await cargarVino(u)
      await irAlCobro(u)
      await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))
      return screen.findByRole('dialog', { name: 'PIN del supervisor' })
    }

    beforeEach(async () => {
      await aplicarBootstrap(bootstrapDeVino(conSupervisor))
    })

    it('el supervisor elegido escribe su PIN correcto: se confirma con su autorizador y sin PIN en el comando', async () => {
      const { u } = montar()
      const dialogo = await hastaElPin(u)

      await u.type(within(dialogo).getByLabelText('PIN de sup01'), PIN_SUP.pin)
      await u.click(within(dialogo).getByRole('button', { name: 'Verificar y confirmar' }))

      expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
      const sobre = (await baseLocal.cola.toArray())[0]?.sobre
      expect(sobre?.contenido.credito).toMatchObject({ resolucion: 'PIN_SUPERVISOR', autorizador_id: SUP01 })
      expect(JSON.stringify(sobre)).not.toContain(PIN_SUP.pin)
      expect(JSON.stringify(await baseLocal.intentos_pin.toArray())).not.toContain(PIN_SUP.pin)
    })

    it('muestra "Verificando…" mientras se deriva el PIN', async () => {
      let terminar: (valor: { tipo: 'ok'; autorizadorId: string }) => void = () => undefined
      mocks.verificar.mockImplementationOnce(() => new Promise((resolver) => (terminar = resolver)))
      const { u } = montar()
      const dialogo = await hastaElPin(u)

      await u.type(within(dialogo).getByLabelText('PIN de sup01'), PIN_SUP.pin)
      await u.click(within(dialogo).getByRole('button', { name: 'Verificar y confirmar' }))

      expect(await within(dialogo).findByText('Verificando…')).toBeInTheDocument()
      terminar({ tipo: 'ok', autorizadorId: SUP01 })
      expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    })

    it('un PIN incorrecto no confirma, informa los intentos que quedan y cuenta el fallo', async () => {
      const { u } = montar()
      const dialogo = await hastaElPin(u)

      await u.type(within(dialogo).getByLabelText('PIN de sup01'), '000000')
      await u.click(within(dialogo).getByRole('button', { name: 'Verificar y confirmar' }))

      expect(await within(dialogo).findByText('PIN incorrecto. Te quedan 4 intentos.')).toBeInTheDocument()
      expect(await baseLocal.ventas.count()).toBe(0)
      expect((await baseLocal.intentos_pin.toArray())[0]).toMatchObject({ fallos: 1, bloqueado: false })
    })

    it('tras 5 fallos queda bloqueado hasta actualizar los datos: ni con el PIN correcto se confirma', async () => {
      const { u } = montar()
      const dialogo = await hastaElPin(u)
      const campo = within(dialogo).getByLabelText('PIN de sup01')

      const verificar = within(dialogo).getByRole('button', { name: 'Verificar y confirmar' })
      for (let i = 0; i < 5; i += 1) {
        await u.clear(campo)
        await u.type(campo, '000000')
        await u.click(verificar)
        await waitFor(async () => expect((await baseLocal.intentos_pin.toArray())[0]?.fallos).toBe(i + 1))
        await waitFor(() => expect(verificar).toBeEnabled())
      }
      await u.clear(campo)
      await u.type(campo, PIN_SUP.pin)
      await u.click(verificar)

      expect(
        await within(dialogo).findByText('El PIN de sup01 está bloqueado en este teléfono hasta que actualices los datos.'),
      ).toBeInTheDocument()
      expect(await baseLocal.ventas.count()).toBe(0)
    })

    it('cancelar el PIN deja el carrito abierto sin guardar nada', async () => {
      const { u } = montar()
      const dialogo = await hastaElPin(u)

      await u.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))

      expect(screen.queryByRole('dialog', { name: 'PIN del supervisor' })).not.toBeInTheDocument()
      expect(await baseLocal.ventas.count()).toBe(0)
      expect(screen.getByTestId('guarda')).toHaveTextContent('carrito abierto')
    })
  })

  it('con motivo obligatorio, el descuento manual ofrece solo los motivos DESCUENTO_MANUAL y la venta sale con el elegido (DSC-05)', async () => {
    await aplicarBootstrap(
      bootstrapDeVino((b) => {
        b.contexto_venta = {
          descuento_manual: { habilitado: true, motivo_obligatorio: true, tiene_permiso: true, tope: '0.100000', puede_autorizar: false },
          puede_superar_credito: false,
        }
        b.catalogos.motivos = [
          { id: ID(21), ambito: 'LISTA_ANTERIOR', nombre: 'Acuerdo de lista' },
          { id: ID(22), ambito: 'DESCUENTO_MANUAL', nombre: 'Cliente frecuente' },
        ]
      }),
    )
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await escribir(u, 'Descuento general (%)', '5')

    const select = await screen.findByLabelText('Motivo del descuento')
    expect(within(select).queryByRole('option', { name: 'Acuerdo de lista' })).not.toBeInTheDocument()
    await u.selectOptions(select, ID(22))
    await irAlCobro(u)
    await u.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    expect(await screen.findByRole('heading', { name: /^Venta 0001-/ })).toBeInTheDocument()
    expect((await baseLocal.cola.toArray())[0]?.sobre.contenido).toMatchObject({ motivo_descuento_id: ID(22) })
  })

  it('un descuento sobre el tope sin permiso propio pide autorizador (DSC-06) y sin supervisor no se confirma', async () => {
    await aplicarBootstrap(bootstrapDeVino())
    const { u } = montar()
    await elegirCliente(u)
    await cargarVino(u)
    await escribir(u, 'Descuento general (%)', '15')
    await irAlCobro(u)

    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeDisabled()
    expect(screen.getByText('Elegí el supervisor que autoriza.')).toBeInTheDocument()
  })
})
