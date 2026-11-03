import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VentaGuardadaScreen } from '../../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { baseLocal, type ObservacionLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../../../utils/datosParaVender'
import { montarEnRuta } from '../../../utils/rutaDePrueba'
import { sembrarAnulacion, sembrarVenta } from '../../../utils/sembrarVenta'

/**
 * Change 22a, tarea 10.3 (spec `ventas/venta-en-ruta`, "La venta confirmada se muestra con su
 * número y su estado"; `design.md` D13, D14; cita VTA-06): número, total, "Sin enviar", "Compartir
 * nota" solo si el navegador comparte archivos, "Descargar nota" y "Nueva venta".
 */
function comparteArchivos(comparte: boolean) {
  Object.defineProperty(window.navigator, 'canShare', {
    configurable: true,
    value: comparte ? () => true : undefined,
  })
}

function montar(ventaId: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/ventas/${ventaId}` },
  )
}

describe('VentaGuardadaScreen (tarea 10.3)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  afterEach(() => comparteArchivos(false))

  it('muestra el número asignado, el total, "Sin enviar" y las acciones de la nota', async () => {
    comparteArchivos(true)
    await sembrarVenta('a')

    montar('venta-a')

    expect(await screen.findByRole('heading', { name: 'Venta 0001-000008' })).toBeInTheDocument()
    expect(screen.getByText('$ 120.000,00')).toBeInTheDocument()
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compartir nota' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Descargar nota' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Nueva venta' })).toHaveAttribute('href', '/ruta/vender')
    expect(screen.getByRole('button', { name: /ayuda: sin enviar/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: número de venta/i })).toBeInTheDocument()
  })

  it('sin Web Share con archivos no ofrece "Compartir nota" pero sí "Descargar nota"', async () => {
    comparteArchivos(false)
    await sembrarVenta('a')

    montar('venta-a')

    expect(await screen.findByRole('button', { name: 'Descargar nota' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Compartir nota' })).not.toBeInTheDocument()
  })

  it('la segunda venta lleva el número siguiente (VTA-06)', async () => {
    await sembrarVenta('a')
    await sembrarVenta('b', { cajas: 0, unidades: 2 })

    montar('venta-b')

    expect(await screen.findByRole('heading', { name: 'Venta 0001-000009' })).toBeInTheDocument()
  })

  it('una venta que no está en el teléfono avisa y vuelve a Ventas de hoy', async () => {
    montar('no-existe')

    expect(await screen.findByText('No encontramos esa venta en este teléfono.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ventas de hoy' })).toHaveAttribute('href', '/ruta/ventas')
  })

  /** Change 22b, tarea 10.3 (cita SYN-04, SYN-09): las etiquetas del detalle. */
  it.each([
    ['ACEPTADA', 'Enviada'],
    ['CON_OBSERVACIONES', 'Con observaciones'],
    ['RECHAZADA', 'Rechazada'],
  ] as const)('el detalle de una venta %s dice «%s»', async (estado, etiqueta) => {
    await sembrarVenta('a')
    await baseLocal.ventas.update('venta-a', { estado_envio: estado })

    montar('venta-a')

    expect(await screen.findByText(etiqueta)).toBeInTheDocument()
    if (estado === 'RECHAZADA') {
      expect((await screen.findByText('Sigue guardada en el teléfono; avisá a administración.'))).toBeInTheDocument()
    }
  })
})

/**
 * Change 22c, tarea 9.2 (spec `ruta/area-de-ruta`, «El detalle de una venta explica sus
 * observaciones o su rechazo»; D3, D4, D5; cita SYN-04, SYN-05, SYN-06, SYN-07).
 */
async function ventaConResultado(
  estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
  resultado: { error_codigo?: string | null; observaciones?: ObservacionLocal[] },
) {
  await sembrarVenta('a')
  await baseLocal.ventas.update('venta-a', { estado_envio: estado })
  const comando = await baseLocal.cola.where('operation_id').equals('op-a').first()
  await baseLocal.cola.update(comando?.secuencia as number, resultado)
}

const observacion = (codigo: string, detalle: Record<string, unknown> | null = null): ObservacionLocal => ({
  codigo,
  operacion_tipo: 'VENTA',
  operacion_id: 'op-a',
  detalle,
})

describe('VentaGuardadaScreen: observaciones y rechazo (change 22c, tarea 9.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('muestra todas las observaciones traducidas, con el medio y el producto de la base local, sin señal', async () => {
    await ventaConResultado('CON_OBSERVACIONES', {
      observaciones: [
        observacion('MEDIO_INACTIVO', { medio_pago_id: IDS_DE_PRUEBA.efectivo }),
        observacion('VENTA_SIN_COSTO', { producto_id: IDS_DE_PRUEBA.producto }),
      ],
    })
    montar('venta-a')

    expect(await screen.findByRole('heading', { name: /^Observaciones/ })).toBeInTheDocument()
    expect(screen.getByText('El medio Efectivo estaba dado de baja cuando llegó el cobro.')).toBeInTheDocument()
    expect(screen.getByText('Gaseosa no tenía costo; la línea quedó sin costo.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /ayuda: observaciones y rechazos/i }).length).toBeGreaterThan(0)
  })

  it('un producto que ya no está en la base local se nombra «un producto»', async () => {
    await ventaConResultado('CON_OBSERVACIONES', {
      observaciones: [observacion('STOCK_NEGATIVO', { producto_id: 'ya-no-esta' })],
    })
    montar('venta-a')

    expect(await screen.findByText('Quedó stock negativo de un producto.')).toBeInTheDocument()
  })

  it('el motivo del rechazo trae el texto, el código y el aviso de que sigue guardada', async () => {
    await ventaConResultado('RECHAZADA', { error_codigo: 'TOTALES_INCONSISTENTES' })
    montar('venta-a')

    expect(await screen.findByRole('heading', { name: /^Motivo del rechazo/ })).toBeInTheDocument()
    expect(screen.getByText('Los importes de la venta no cierran con el cálculo del sistema.')).toBeInTheDocument()
    expect(screen.getByText('TOTALES_INCONSISTENTES')).toBeInTheDocument()
    expect(screen.getByText('Sigue guardada en el teléfono; avisá a administración.')).toBeInTheDocument()
  })

  it('una «Con observaciones» sin la lista guardada dice que el detalle no está en el teléfono', async () => {
    await ventaConResultado('CON_OBSERVACIONES', {})
    montar('venta-a')

    expect(await screen.findByText('El detalle no está en el teléfono; consultalo con administración.')).toBeInTheDocument()
  })

  it('una «Enviada» no muestra ninguna de las dos secciones', async () => {
    await ventaConResultado('ACEPTADA', { observaciones: [] })
    montar('venta-a')

    await screen.findByText('Enviada')
    expect(screen.queryByRole('heading', { name: /^Observaciones/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^Motivo del rechazo/ })).not.toBeInTheDocument()
  })
})

/**
 * Change 22d, tarea 10.2 (spec `ruta/area-de-ruta`, «Las anulaciones se ven en las pantallas de
 * ruta»: «Anulación con observaciones», «Anulación rechazada» y «Doble sincronización»; `design.md`
 * D10, D11; cita VTA-20, SYN-06, SYN-07, INV-06): la etiqueta «Anulada» y la sección «Anulación».
 */
async function anulacionConResultado(
  estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
  resultado: { error_codigo?: string | null; observaciones?: ObservacionLocal[] },
  opciones: { devuelveDinero?: boolean | null; observacion?: string | null; cobro?: string } = {},
) {
  await sembrarVenta('a', opciones.cobro === undefined ? {} : { cobro: opciones.cobro })
  await sembrarAnulacion('a', { devuelveDinero: opciones.devuelveDinero ?? null, observacion: opciones.observacion ?? null })
  await baseLocal.anulaciones.update('venta-a', { estado_envio: estado })
  const comando = await baseLocal.cola.where('operation_id').equals('op-anul-a').first()
  await baseLocal.cola.update(comando?.secuencia as number, resultado)
}

describe('VentaGuardadaScreen: la anulación (change 22d, tarea 10.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('una venta anulada se ve «Anulada» y la sección «Anulación» dice motivo, observación, estado «Sin enviar» y la ayuda', async () => {
    await sembrarVenta('a')
    await sembrarAnulacion('a', { observacion: 'Se cargó dos veces' })

    montar('venta-a')

    expect(await screen.findByText('Anulada')).toBeInTheDocument()
    const seccion = await screen.findByRole('region', { name: 'Anulación' })
    expect(within(seccion).getByText('Error de carga')).toBeInTheDocument()
    expect(within(seccion).getByText('Se cargó dos veces')).toBeInTheDocument()
    expect(within(seccion).getByText('Sin enviar')).toBeInTheDocument()
    expect(within(seccion).queryByText(/lo cobrado/i)).not.toBeInTheDocument()
    expect(within(seccion).getByRole('button', { name: /ayuda: sin enviar/i })).toBeInTheDocument()
  })

  it('con cobro y devolución dice que se devolvió lo cobrado (VTA-22)', async () => {
    await anulacionConResultado('ACEPTADA', {}, { cobro: '30000.00', devuelveDinero: true })
    montar('venta-a')

    const seccion = await screen.findByRole('region', { name: 'Anulación' })
    expect(within(seccion).getByText('Se devolvió lo cobrado.')).toBeInTheDocument()
    expect(within(seccion).getByText('Enviada')).toBeInTheDocument()
  })

  it('sin devolución dice que lo cobrado quedó a favor del cliente (VTA-22)', async () => {
    await anulacionConResultado('ACEPTADA', {}, { cobro: '30000.00', devuelveDinero: false })
    montar('venta-a')

    const seccion = await screen.findByRole('region', { name: 'Anulación' })
    expect(within(seccion).getByText('Lo cobrado quedó a favor del cliente.')).toBeInTheDocument()
  })

  it('«Con observaciones» explica con el texto de la anulación y la ayuda de observaciones (SYN-07)', async () => {
    await anulacionConResultado('CON_OBSERVACIONES', {
      observaciones: [{ codigo: 'JORNADA_LIBERADA', operacion_tipo: 'VENTA_ANULAR', operacion_id: 'op-anul-a', detalle: null }],
    })
    montar('venta-a')

    const seccion = await screen.findByRole('region', { name: 'Anulación' })
    expect(within(seccion).getByText('Con observaciones')).toBeInTheDocument()
    expect(await within(seccion).findByText('La jornada había sido liberada cuando llegó la anulación.')).toBeInTheDocument()
    expect(within(seccion).getAllByRole('button', { name: /ayuda: observaciones y rechazos/i }).length).toBeGreaterThan(0)
  })

  it('«Rechazada» trae el texto de la anulación, el código, «La venta sigue vigente…» y la ayuda de anulación rechazada (SYN-06)', async () => {
    await anulacionConResultado('RECHAZADA', { error_codigo: 'VENTA_YA_ANULADA' })
    montar('venta-a')

    const seccion = await screen.findByRole('region', { name: 'Anulación' })
    expect(await within(seccion).findByText('La venta ya estaba anulada en el sistema.')).toBeInTheDocument()
    expect(within(seccion).getByText('VENTA_YA_ANULADA')).toBeInTheDocument()
    expect(within(seccion).getByText('La venta sigue vigente en el teléfono; avisá a administración.')).toBeInTheDocument()
    expect(within(seccion).getByRole('button', { name: /ayuda: anulación rechazada/i })).toBeInTheDocument()
  })

  it('una anulación rechazada no marca la venta como «Anulada»: sigue vigente', async () => {
    await anulacionConResultado('RECHAZADA', { error_codigo: 'VENTA_YA_ANULADA' })
    montar('venta-a')

    await screen.findByRole('region', { name: 'Anulación' })
    expect(screen.queryByText('Anulada')).not.toBeInTheDocument()
  })

  it('una venta sin anulación no tiene sección «Anulación» ni «Anulada»', async () => {
    await sembrarVenta('a')
    montar('venta-a')

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('region', { name: 'Anulación' })).not.toBeInTheDocument()
    expect(screen.queryByText('Anulada')).not.toBeInTheDocument()
  })

  it('escribir dos veces el mismo resultado muestra lo mismo (INV-06)', async () => {
    await anulacionConResultado('CON_OBSERVACIONES', {
      observaciones: [{ codigo: 'JORNADA_LIBERADA', operacion_tipo: 'VENTA_ANULAR', operacion_id: 'op-anul-a', detalle: null }],
    })
    montar('venta-a')
    await screen.findByText('La jornada había sido liberada cuando llegó la anulación.')
    const antes = (await screen.findByRole('region', { name: 'Anulación' })).textContent

    await baseLocal.anulaciones.update('venta-a', { estado_envio: 'CON_OBSERVACIONES' })

    expect((await screen.findByRole('region', { name: 'Anulación' })).textContent).toBe(antes)
  })
})

vi.mock('../../../../../src/lib/nota/pdf', () => ({ generarPdfDeNota: vi.fn(async () => new Blob(['pdf'])) }))
