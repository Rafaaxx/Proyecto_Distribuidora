import 'fake-indexeddb/auto'

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { components } from '../../../../src/api/schema.gen'

const mocks = vi.hoisted(() => ({ dispararTrasVenta: vi.fn() }))
vi.mock('../../../../src/sync/disparadores', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../src/sync/disparadores')>()
  return { ...real, dispararTrasVenta: mocks.dispararTrasVenta }
})

import { leerSaldoConsiderado } from '../../../../src/areas/ruta/datos/disponibles'
import { CobrarScreen } from '../../../../src/areas/ruta/cobranzas/CobrarScreen'
import { ClienteFichaScreen } from '../../../../src/areas/ruta/clientes/ClienteFichaScreen'
import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { useGuardaDelCarrito } from '../../../../src/areas/ruta/ventas/contextoGuarda'
import { ProveedorGuardaDelCarrito } from '../../../../src/areas/ruta/ventas/guardaDelCarrito'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 23, tarea 7.1 (spec `ruta/area-de-ruta`, «Se cobra a un cliente desde el teléfono», sus
 * nueve escenarios; `design.md` D3, D4, D8; cita COB-01, COB-02, INV-08, CLI-03, SYN-10, SEG-06,
 * CC-04, INV-03): «Cobrar» en el inicio y en la ficha con permiso; el selector sin el consumidor
 * final; las validaciones; la confirmación; el saldo a favor; la guarda «¿Descartar la cobranza?».
 * Almacén Uno debe $1.500,50 (cartera); Kiosco Dos también.
 */
const TRANSFERENCIA = ID(23)
const CONSUMIDOR_FINAL = ID(150)

function bootstrapDeCobranza(cambios: (b: Bootstrap) => void = () => undefined): Bootstrap {
  return bootstrapParaVender((b) => {
    b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
    b.catalogos.medios_pago = [
      { id: IDS_DE_PRUEBA.efectivo, nombre: 'Efectivo', requiere_referencia: false },
      { id: TRANSFERENCIA, nombre: 'Transferencia', requiere_referencia: true },
    ]
    cambios(b)
  })
}

function Ubicacion() {
  const { pathname, search } = useLocation()
  return <p data-testid="ubicacion">{pathname + search}</p>
}

function Sonda() {
  const { ocupado } = useGuardaDelCarrito()
  return <p data-testid="guarda">{ocupado ? 'ocupada' : 'libre'}</p>
}

function montar(ruta = '/ruta/cobrar') {
  const vista = montarEnRuta(
    <ProveedorGuardaDelCarrito>
      <Ubicacion />
      <Sonda />
      <Routes>
        <Route path="/ruta/cobrar" element={<CobrarScreen />} />
        <Route path="/ruta/cobranzas/:id" element={<h1>Cobranza guardada</h1>} />
        <Route path="/ruta" element={<h1>Inicio de ruta</h1>} />
      </Routes>
    </ProveedorGuardaDelCarrito>,
    { ruta },
  )
  return { ...vista, u: userEvent.setup() }
}

type Usuario = ReturnType<typeof userEvent.setup>

async function cargarImporte(u: Usuario, importe: string) {
  await u.type(await screen.findByLabelText('Importe a cobrar'), importe)
}

async function cargarMedio(u: Usuario, n: number, medio: string, importe: string, referencia?: string) {
  await u.selectOptions(await screen.findByLabelText(`Medio de cobro ${n}`), medio)
  await u.type(screen.getByLabelText(`Importe del medio ${n}`), importe)
  if (referencia !== undefined) await u.type(screen.getByLabelText(`Referencia del medio ${n}`), referencia)
}

async function cobranzas() {
  return baseLocal.cobranzas.toArray()
}

describe('CobrarScreen (tarea 7.1)', () => {
  beforeEach(async () => {
    mocks.dispararTrasVenta.mockReset()
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapDeCobranza())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('cobra sin señal con dos medios (uno con referencia): guarda, encola, dispara el envío y va a «Cobranza guardada» (COB-01, COB-02, COB-04)', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Saldo actual: $ 1.500,50')

    await cargarImporte(u, '500.00')
    await cargarMedio(u, 1, 'Efectivo', '300.00')
    await u.click(screen.getByRole('button', { name: 'Agregar medio de cobro' }))
    await cargarMedio(u, 2, 'Transferencia', '200.00', '0042')
    expect(screen.getByTestId('saldo-despues')).toHaveTextContent('Saldo después del cobro: $ 1.000,50')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByRole('heading', { name: '¿Registrar la cobranza de $ 500,00 a Almacén Uno?' })).toBeInTheDocument()
    expect(screen.queryByText(/a favor/)).not.toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Registrar' }))

    expect(await screen.findByRole('heading', { name: 'Cobranza guardada' })).toBeInTheDocument()
    const guardada = (await cobranzas())[0]
    expect(guardada).toMatchObject({
      origen: 'INDEPENDIENTE',
      venta_id: null,
      cliente_id: IDS_DE_PRUEBA.cliente,
      total: '500.00',
      estado_envio: 'PENDIENTE',
      medios: [
        { medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '300.00', referencia: null },
        { medio_pago_id: TRANSFERENCIA, importe: '200.00', referencia: '0042' },
      ],
    })
    expect(await baseLocal.cola.count()).toBe(1)
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('1000.50')
    expect(mocks.dispararTrasVenta).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('ubicacion')).toHaveTextContent(`/ruta/cobranzas/${guardada?.cobranza_id}`)
  })

  it('los medios que no suman el importe no confirman y se indica la diferencia (INV-08, COB-02)', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '500.00')
    await cargarMedio(u, 1, 'Efectivo', '490.00')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('Los medios no suman el importe: faltan $ 10,00.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar' })).not.toBeInTheDocument()
    expect(await cobranzas()).toHaveLength(0)
    expect(await baseLocal.cola.count()).toBe(0)
  })

  it('si los medios suman de más, dice cuánto sobra', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '500.00')
    await cargarMedio(u, 1, 'Efectivo', '520.50')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('Los medios no suman el importe: sobran $ 20,50.')).toBeInTheDocument()
  })

  it.each(['', '   '])('un medio que exige referencia sin ella (%j) no confirma y se pide la referencia (COB-02)', async (referencia) => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '500.00')
    await cargarMedio(u, 1, 'Transferencia', '500.00')
    if (referencia !== '') await u.type(screen.getByLabelText('Referencia del medio 1'), referencia)
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('Falta la referencia de un medio que la pide.')).toBeInTheDocument()
    expect(await cobranzas()).toHaveLength(0)
  })

  it.each(['0', '-5', '10.123', ''])('el importe %j no confirma (COB-01, INV-03)', async (importe) => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    if (importe !== '') await cargarImporte(u, importe)
    await cargarMedio(u, 1, 'Efectivo', importe === '' ? '10.00' : importe)
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('El importe tiene que ser mayor que cero y tener hasta dos decimales.')).toBeInTheDocument()
    expect(await cobranzas()).toHaveLength(0)
  })

  it('una observación de más de 500 caracteres no confirma', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '10.00')
    await cargarMedio(u, 1, 'Efectivo', '10.00')
    const observacion = screen.getByLabelText('Observación (opcional)')
    await u.click(observacion)
    await u.paste('x'.repeat(501))
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('La observación puede tener hasta 500 caracteres.')).toBeInTheDocument()
    expect(await cobranzas()).toHaveLength(0)
  })

  it('si el saldo resultante queda a favor, avisa «El cliente queda con {importe} a favor.» y solo guarda si lo confirma (CC-04)', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '2000.00')
    await cargarMedio(u, 1, 'Efectivo', '2000.00')
    expect(screen.getByTestId('saldo-despues')).toHaveTextContent('Saldo después del cobro: $ -499,50')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))

    expect(await screen.findByText('El cliente queda con $ 499,50 a favor.')).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Volver' }))
    expect(await cobranzas()).toHaveLength(0)

    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))
    await u.click(await screen.findByRole('button', { name: 'Registrar' }))
    expect(await screen.findByRole('heading', { name: 'Cobranza guardada' })).toBeInTheDocument()
    expect(await leerSaldoConsiderado(IDS_DE_PRUEBA.cliente)).toBe('-499.50')
  })

  it('el doble toque en «Registrar» guarda una sola cobranza (INV-06)', async () => {
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '10.00')
    await cargarMedio(u, 1, 'Efectivo', '10.00')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))
    const registrar = await screen.findByRole('button', { name: 'Registrar' })
    await u.dblClick(registrar)

    await screen.findByRole('heading', { name: 'Cobranza guardada' })
    expect(await cobranzas()).toHaveLength(1)
    expect(await baseLocal.cola.count()).toBe(1)
  })

  it('sin cliente elegido ofrece el selector con la cartera primero y sin el consumidor final (CLI-03)', async () => {
    await baseLocal.clientes.clear()
    await aplicarBootstrap(
      bootstrapDeCobranza((b) => {
        b.clientes = [
          { ...b.clientes[1]!, nombre: 'Zeta fuera de cartera', en_cartera: false },
          b.clientes[0]!,
          {
            ...b.clientes[0]!,
            id: CONSUMIDOR_FINAL,
            nombre: 'Consumidor final',
            es_consumidor_final: true,
            en_cartera: false,
            saldo: '0.00',
          },
        ]
      }),
    )
    const { u } = montar()

    const botones = await screen.findAllByRole('button', { name: /Almacén Uno|Zeta fuera de cartera|Consumidor final/ })
    expect(botones.map((b) => b.textContent)).toEqual([expect.stringContaining('Almacén Uno'), expect.stringContaining('Zeta fuera de cartera')])

    await u.click(botones[1] as HTMLElement)
    expect(await screen.findByTestId('saldo-actual')).toBeInTheDocument()
    expect(screen.getByText('Zeta fuera de cartera')).toBeInTheDocument()
  })

  it('el consumidor final pedido por la dirección no se cobra (CLI-03)', async () => {
    await baseLocal.clientes.clear()
    await aplicarBootstrap(
      bootstrapDeCobranza((b) => {
        b.clientes = [{ ...b.clientes[0]!, id: CONSUMIDOR_FINAL, nombre: 'Consumidor final', es_consumidor_final: true, saldo: '0.00' }]
      }),
    )
    montar('/ruta/cobrar?cliente=' + CONSUMIDOR_FINAL)

    expect(await screen.findByText('No hay clientes que coincidan con la búsqueda.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Importe a cobrar')).not.toBeInTheDocument()
  })

  it('cobra a un cliente suspendido que no está en la cartera sin aviso (COB-01, 01 §19)', async () => {
    await baseLocal.clientes.clear()
    await aplicarBootstrap(
      bootstrapDeCobranza((b) => {
        b.clientes = [{ ...b.clientes[0]!, estado: 'SUSPENDIDO', en_cartera: false }]
      }),
    )
    const { u } = montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)
    await cargarImporte(u, '10.00')
    await cargarMedio(u, 1, 'Efectivo', '10.00')
    await u.click(screen.getByRole('button', { name: 'Confirmar cobranza' }))
    expect(screen.queryByText(/suspendido/i)).not.toBeInTheDocument()
    await u.click(await screen.findByRole('button', { name: 'Registrar' }))

    expect(await screen.findByRole('heading', { name: 'Cobranza guardada' })).toBeInTheDocument()
    expect(await cobranzas()).toHaveLength(1)
  })

  it('sin REGISTRAR_COBRANZA no se puede cobrar (SYN-10, SEG-06)', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
    montar('/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente)

    expect(await screen.findByText('No tenés permiso para cobrar.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Importe a cobrar')).not.toBeInTheDocument()
  })

  it('sin datos del día avisa que faltan', async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    montar()

    expect(await screen.findByText('Cobrar necesita los datos del día: abrí la jornada para descargarlos.')).toBeInTheDocument()
  })

  it('con un importe cargado, salir pregunta «¿Descartar la cobranza?», marca la guarda y, si no confirma, sigue con los datos (02 §13.5)', async () => {
    const { u, router } = await montarConEnrutadorDeDatos()
    await cargarImporte(u, '500.00')
    await waitFor(() => expect(screen.getByTestId('guarda')).toHaveTextContent('ocupada'))

    await router.navigate('/ruta')
    expect(await screen.findByRole('heading', { name: '¿Descartar la cobranza?' })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Seguir cobrando' }))
    expect(screen.getByLabelText('Importe a cobrar')).toHaveValue('500.00')
    expect(screen.getByTestId('ubicacion')).toHaveTextContent('/ruta/cobrar')

    await router.navigate('/ruta')
    await u.click(await screen.findByRole('button', { name: 'Descartar' }))
    expect(await screen.findByRole('heading', { name: 'Inicio de ruta' })).toBeInTheDocument()
    expect(screen.getByTestId('guarda')).toHaveTextContent('libre')
    expect(await cobranzas()).toHaveLength(0)
  })

  it('sin datos cargados salir no pregunta nada y la guarda queda libre', async () => {
    const { router } = await montarConEnrutadorDeDatos()
    await screen.findByLabelText('Importe a cobrar')
    expect(screen.getByTestId('guarda')).toHaveTextContent('libre')

    await router.navigate('/ruta')
    expect(await screen.findByRole('heading', { name: 'Inicio de ruta' })).toBeInTheDocument()
  })
})

async function montarConEnrutadorDeDatos() {
  const { createMemoryRouter, RouterProvider } = await import('react-router-dom')
  const { render } = await import('@testing-library/react')
  const { ContextoSesion } = await import('../../../../src/areas/ruta/sesion/contextoSesion')
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: (
          <ContextoSesion.Provider
            value={{
              entrada: { tipo: 'al_dia' },
              alCerrarSesion: vi.fn(),
              alBloquearse: vi.fn(),
              reintentarEntrada: vi.fn(async () => undefined),
            }}
          >
            <ProveedorGuardaDelCarrito>
              <Ubicacion />
              <Sonda />
              <Routes>
                <Route path="/ruta/cobrar" element={<CobrarScreen />} />
                <Route path="/ruta" element={<h1>Inicio de ruta</h1>} />
              </Routes>
            </ProveedorGuardaDelCarrito>
          </ContextoSesion.Provider>
        ),
      },
    ],
    { initialEntries: ['/ruta/cobrar?cliente=' + IDS_DE_PRUEBA.cliente] },
  )
  render(<RouterProvider router={router} />)
  return { router, u: userEvent.setup() }
}

describe('«Cobrar» en el inicio y en la ficha (tarea 7.1)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('con REGISTRAR_COBRANZA el inicio ofrece «Cobrar» y «Cobranzas de hoy»', async () => {
    await aplicarBootstrap(bootstrapDeCobranza())
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Cobrar' })).toHaveAttribute('href', '/ruta/cobrar')
    expect(screen.getByRole('link', { name: 'Cobranzas de hoy' })).toHaveAttribute('href', '/ruta/cobranzas')
  })

  it('sin REGISTRAR_COBRANZA el inicio no ofrece «Cobrar» (SYN-10, SEG-06)', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    montarEnRuta(<InicioScreen />)

    await screen.findByRole('link', { name: 'Vender' })
    expect(screen.queryByRole('link', { name: 'Cobrar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cobrar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cobranzas de hoy' })).not.toBeInTheDocument()
  })

  it('con REGISTRAR_COBRANZA la ficha ofrece «Cobrar» con el cliente elegido', async () => {
    await aplicarBootstrap(bootstrapDeCobranza())
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${IDS_DE_PRUEBA.cliente}` },
    )

    expect(await screen.findByRole('link', { name: 'Cobrar' })).toHaveAttribute('href', `/ruta/cobrar?cliente=${IDS_DE_PRUEBA.cliente}`)
  })

  it('la ficha del consumidor final no ofrece «Cobrar» (CLI-03)', async () => {
    await aplicarBootstrap(
      bootstrapDeCobranza((b) => {
        b.clientes = [{ ...b.clientes[0]!, id: CONSUMIDOR_FINAL, nombre: 'Consumidor final', es_consumidor_final: true, saldo: '0.00' }]
      }),
    )
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${CONSUMIDOR_FINAL}` },
    )

    expect(await screen.findByRole('heading', { name: 'Consumidor final' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cobrar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cobrar' })).not.toBeInTheDocument()
  })

  it('la ficha sin REGISTRAR_COBRANZA no ofrece «Cobrar»', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${IDS_DE_PRUEBA.cliente}` },
    )

    expect(await screen.findByRole('link', { name: 'Vender' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cobrar' })).not.toBeInTheDocument()
  })

  it('el botón de cada pantalla no repite el motivo cuando Vender ya lo muestra', async () => {
    await aplicarBootstrap(bootstrapDeCobranza())
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })

    const cobrar = await screen.findByRole('button', { name: 'Cobrar' })
    expect(cobrar).toBeDisabled()
    expect(within(document.body).getAllByText('Vender requiere una jornada abierta.')).toHaveLength(1)
  })
})
