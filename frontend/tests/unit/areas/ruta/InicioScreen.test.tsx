import 'fake-indexeddb/auto'

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapDePrueba } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { sembrarVenta } from '../../utils/sembrarVenta'
import { montarEnRuta } from '../../utils/rutaDePrueba'

const mocks = vi.hoisted(() => ({ pedirBootstrap: vi.fn() }))
vi.mock('../../../../src/sync/clienteBootstrap', () => ({ pedirBootstrap: mocks.pedirBootstrap }))

import { InicioScreen } from '../../../../src/areas/ruta/InicioScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { formatearFechaHora } from '../../../../src/lib/fecha'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 21, tarea 13.1 (spec `ruta/area-de-ruta`, "El inicio muestra la jornada, la conexión y
 * los datos"; cita RUT-03, RUT-09, SYN-11; D18, D21): usuario, jornada, conexión, hora de los datos,
 * "Actualizar datos", advertencia de almacenamiento, jornada liberada y accesos.
 */
function conectado(valor: boolean) {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(valor)
}

function almacenamiento(concede: boolean) {
  Object.defineProperty(window.navigator, 'storage', {
    configurable: true,
    value: { persisted: vi.fn(async () => false), persist: vi.fn(async () => concede) },
  })
}

async function sembrar(permisos: string[] = ['VENDER']) {
  const b = bootstrapDePrueba()
  b.sesion.permisos = permisos
  await aplicarBootstrap(b)
  return b
}

describe('InicioScreen (tarea 13.1)', () => {
  beforeEach(async () => {
    mocks.pedirBootstrap.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
    almacenamiento(true)
  })
  afterEach(() => {
    vi.restoreAllMocks()
    Reflect.deleteProperty(window.navigator, 'storage')
  })

  it('muestra usuario, ubicación de la jornada, conexión, hora de los datos y los accesos', async () => {
    const b = await sembrar()
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(/Vendedor Uno/)).toBeInTheDocument()
    expect(screen.getByText(/Camioneta 1/)).toBeInTheDocument()
    expect(screen.getByText('Con conexión')).toBeInTheDocument()
    expect(screen.getByText(`Datos de ${formatearFechaHora(b.generado_en)}`)).toBeInTheDocument()
    for (const acceso of ['Clientes', 'Productos', 'Stock', 'Mi cuenta', 'Ayuda']) {
      expect(screen.getByRole('link', { name: acceso })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Ayuda: Datos del día' })).toBeInTheDocument()
    expect(screen.queryByText(/puede borrar los datos/i)).not.toBeInTheDocument()
  })

  it('sin conexión: lo dice y "Actualizar datos" queda deshabilitado con su motivo', async () => {
    conectado(false)
    await sembrar()
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('Sin conexión')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actualizar datos' })).toBeDisabled()
    expect(screen.getByText(/actualizar requiere conexión/i)).toBeInTheDocument()
  })

  it('"Actualizar datos" baja el bootstrap, reemplaza los datos y muestra la hora nueva', async () => {
    await sembrar()
    const nuevo = bootstrapDePrueba({ generado: '2026-10-30T15:30:00Z' })
    mocks.pedirBootstrap.mockResolvedValue({ tipo: 'ok', bootstrap: nuevo })
    montarEnRuta(<InicioScreen />)

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Actualizar datos' }))

    expect(await screen.findByText(`Datos de ${formatearFechaHora(nuevo.generado_en)}`)).toBeInTheDocument()
    expect(mocks.pedirBootstrap).toHaveBeenCalledTimes(1)
  })

  it('si actualizar falla, avisa y "Reintentar" vuelve a pedir; los datos anteriores siguen', async () => {
    const b = await sembrar()
    mocks.pedirBootstrap.mockResolvedValueOnce({ tipo: 'error', estado: 500 })
    mocks.pedirBootstrap.mockResolvedValueOnce({
      tipo: 'ok',
      bootstrap: bootstrapDePrueba({ generado: '2026-10-30T16:00:00Z' }),
    })
    montarEnRuta(<InicioScreen />)
    const u = userEvent.setup()

    await u.click(await screen.findByRole('button', { name: 'Actualizar datos' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudieron actualizar/i)
    expect(screen.getByText(`Datos de ${formatearFechaHora(b.generado_en)}`)).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(mocks.pedirBootstrap).toHaveBeenCalledTimes(2)
  })

  it('un error al entrar ofrece "Reintentar", que vuelve a consultar la jornada', async () => {
    await sembrar()
    const { sesion } = montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'error' } } })

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(sesion.reintentarEntrada).toHaveBeenCalledTimes(1)
  })

  it('el almacenamiento negado muestra la advertencia permanente con su "(?)"', async () => {
    almacenamiento(false)
    await sembrar()
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(/puede borrar los datos de esta aplicación/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Almacenamiento del teléfono' })).toBeInTheDocument()
  })

  it('la advertencia de almacenamiento se ajusta al ancho del teléfono (texto que parte línea)', async () => {
    almacenamiento(false)
    await sembrar()
    montarEnRuta(<InicioScreen />)

    const aviso = await screen.findByTestId('aviso-almacenamiento')
    expect(aviso).toHaveClass('w-full', 'min-w-0', 'max-w-full')
    expect(screen.getByText(/puede borrar los datos de esta aplicación/i)).toHaveClass('min-w-0', 'flex-1', 'break-words')
  })

  it('jornada liberada: con conexión informa que ya no está abierta y ofrece abrir otra', async () => {
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })

    expect(await screen.findByText(/tu jornada ya no figura abierta/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir jornada' })).toHaveAttribute('href', '/ruta/jornada/abrir')
  })

  it('sin jornada y sin conexión: "Abrir jornada" deshabilitado y dice que requiere conexión', async () => {
    conectado(false)
    await sembrar(['VENDER', 'ABRIR_JORNADA'])
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })

    expect(await screen.findByRole('button', { name: 'Abrir jornada' })).toBeDisabled()
    expect(screen.getByText(/abrir la jornada requiere conexión/i)).toBeInTheDocument()
  })

  it('sin el permiso ABRIR_JORNADA no se ofrece abrir la jornada', async () => {
    await sembrar(['VENDER'])
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })

    expect(await screen.findByText(/tu jornada ya no figura abierta/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Abrir jornada' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir jornada' })).not.toBeInTheDocument()
  })

  it('sin ningún bootstrap todavía: avisa que no hay datos descargados', async () => {
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })
    expect(await screen.findByText(/todavía no hay datos descargados/i)).toBeInTheDocument()
  })
})

/**
 * Change 22a, tarea 11.2 (spec `ruta/area-de-ruta`, "El inicio muestra las ventas sin enviar";
 * `design.md` D13, D14; cita SYN-09, RUT-03): "N ventas sin enviar" / "Todo enviado", y "Vender"
 * y "Ventas de hoy" con el permiso y los datos que corresponden.
 */
describe('InicioScreen: ventas sin enviar y "Vender" (tarea 11.2)', () => {
  beforeEach(async () => {
    mocks.pedirBootstrap.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    conectado(true)
    almacenamiento(true)
  })
  afterEach(() => {
    vi.restoreAllMocks()
    Reflect.deleteProperty(window.navigator, 'storage')
  })

  it('con dos ventas confirmadas dice "2 ventas sin enviar"', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 0, unidades: 2 })
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('2 ventas sin enviar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Sin enviar' })).toBeInTheDocument()
  })

  it('con una sola venta usa el singular y sin ventas dice "Todo enviado"', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    montarEnRuta(<InicioScreen />)
    expect(await screen.findByText('Todo enviado')).toBeInTheDocument()

    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    expect(await screen.findByText('1 venta sin enviar')).toBeInTheDocument()
  })

  it('las ventas sin enviar de otro usuario del teléfono no se cuentan como propias', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a', { cajas: 1, unidades: 0, usuarioId: 'otro-usuario' })
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText('Todo enviado')).toBeInTheDocument()
  })

  it('con VENDER y la jornada abierta ofrece "Vender" y "Ventas de hoy"', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByRole('link', { name: 'Vender' })).toHaveAttribute('href', '/ruta/vender')
    expect(screen.getByRole('link', { name: 'Ventas de hoy' })).toHaveAttribute('href', '/ruta/ventas')
  })

  it('sin VENDER entre los permisos del bootstrap no aparece "Vender"', async () => {
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.sesion.permisos = ['CONSULTAR_STOCK']
      }),
    )
    montarEnRuta(<InicioScreen />)

    expect(await screen.findByText(/Hola, Vendedor Uno/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Vender' })).not.toBeInTheDocument()
  })

  it('sin datos del día "Vender" no está disponible y se indica que faltan los datos', async () => {
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_red' } } })

    expect(await screen.findByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.getByText('Vender necesita los datos del día: abrí la jornada para descargarlos.')).toBeInTheDocument()
  })

  it('con la jornada liberada "Vender" queda deshabilitado con su motivo', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    montarEnRuta(<InicioScreen />, { sesion: { entrada: { tipo: 'sin_jornada' } } })

    expect(await screen.findByRole('button', { name: 'Vender' })).toBeDisabled()
    expect(screen.getByText('Vender requiere una jornada abierta.')).toBeInTheDocument()
  })
})

