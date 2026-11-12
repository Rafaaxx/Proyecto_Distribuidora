import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { CobranzaGuardadaScreen } from '../../../../../src/areas/ruta/cobranzas/CobranzaGuardadaScreen'
import { CobranzasDeHoyScreen } from '../../../../../src/areas/ruta/cobranzas/CobranzasDeHoyScreen'
import { baseLocal, type ObservacionLocal } from '../../../../../src/lib/dispositivo/db'
import { formatearFechaHora } from '../../../../../src/lib/fecha'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../../../utils/datosParaVender'
import { montarEnRuta } from '../../../utils/rutaDePrueba'
import { sembrarCobranza, sembrarVenta } from '../../../utils/sembrarVenta'

/**
 * Change 23, tarea 8.1 (spec `ruta/area-de-ruta`, «Las cobranzas se ven en las pantallas de ruta»,
 * escenarios «Cobranzas de hoy», «Cobranza con observaciones», «Código desconocido» y «Doble
 * sincronización»; `design.md` D8, D9; cita SYN-07, SYN-09, INV-06): la lista de la jornada y el
 * detalle con medios, estado y explicación; sin comprobante.
 */
const obs = (codigo: string, detalle: Record<string, unknown> | null = null): ObservacionLocal => ({
  codigo,
  operacion_tipo: 'COBRANZA',
  operacion_id: 'op',
  detalle,
})

async function conResultado(
  sufijo: string,
  estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
  resultado: { error_codigo?: string | null; observaciones?: ObservacionLocal[] } = {},
) {
  await baseLocal.cobranzas.update(`cobranza-s-${sufijo}`, { estado_envio: estado })
  const comando = await baseLocal.cola.where('operation_id').equals(`op-cob-${sufijo}`).first()
  await baseLocal.cola.update(comando?.secuencia as number, {
    estado: estado === 'RECHAZADA' ? 'RECHAZADO' : estado === 'ACEPTADA' ? 'ACEPTADO' : 'ACEPTADO_CON_OBSERVACIONES',
    ...resultado,
  })
}

function montarDetalle(id: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/cobranzas/:id" element={<CobranzaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/cobranzas/${id}` },
  )
}

describe('Cobranzas de hoy (tarea 8.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
      }),
    )
  })

  it('lista las cobranzas de la jornada con cliente, importe, hora y estado, la más nueva primero (SYN-09)', async () => {
    await sembrarCobranza('a', { importe: '100.00', ahora: new Date('2026-10-30T15:00:00.000Z') })
    await sembrarCobranza('b', { importe: '250.50', ahora: new Date('2026-10-30T16:00:00.000Z') })
    await conResultado('a', 'ACEPTADA')
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    expect(await screen.findByRole('heading', { name: 'Cobranzas de hoy' })).toBeInTheDocument()
    const filas = await screen.findAllByRole('listitem')
    expect(filas).toHaveLength(2)
    expect(within(filas[0] as HTMLElement).getByText('$ 250,50')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText('Almacén Uno')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText('Sin enviar')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText(formatearFechaHora('2026-10-30T16:00:00.000Z').trim())).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('$ 100,00')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('Enviada')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByRole('link')).toHaveAttribute('href', '/ruta/cobranzas/cobranza-s-a')
  })

  it('no lista el cobro de una venta ni las cobranzas de otra jornada', async () => {
    await sembrarVenta('v', { cobro: '10.00' })
    await sembrarCobranza('a')
    await baseLocal.cobranzas.put({
      cobranza_id: 'cobranza-ajena',
      venta_id: null,
      operation_id: 'op-ajena',
      jornada_id: 'otra-jornada',
      origen: 'INDEPENDIENTE',
      cliente_id: IDS_DE_PRUEBA.cliente,
      cliente_nombre: 'Ajeno',
      occurred_at: '2026-10-30T10:00:00.000Z',
      estado_envio: 'PENDIENTE',
      medios: [],
      total: '1.00',
    })
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    const filas = await screen.findAllByRole('listitem')
    expect(filas).toHaveLength(1)
    expect(screen.queryByText('Ajeno')).not.toBeInTheDocument()
  })

  it('sin cobranzas dice que todavía no hay ninguna', async () => {
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    expect(await screen.findByText('Todavía no hiciste cobranzas en esta jornada.')).toBeInTheDocument()
  })

  it('una cobranza rechazada trae la ayuda de cobranza rechazada', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'RECHAZADA', { error_codigo: 'RECURSO_NO_ENCONTRADO' })
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    await screen.findByText('Rechazada')
    expect(screen.getByRole('button', { name: /ayuda: cobranza rechazada/i })).toBeInTheDocument()
  })

  it('actualizar los resultados dos veces con lo mismo no cambia la lista (INV-06)', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'ACEPTADA')
    await conResultado('a', 'ACEPTADA')
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    const filas = await screen.findAllByRole('listitem')
    expect(filas).toHaveLength(1)
    expect(within(filas[0] as HTMLElement).getByText('Enviada')).toBeInTheDocument()
  })
})

describe('Cobranza guardada (tarea 8.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
      }),
    )
  })

  it('muestra cliente, importe, medios con su referencia, observación, momento y «Sin enviar», sin comprobante (D9)', async () => {
    await sembrarCobranza('a', { importe: '100.00', observacion: 'Pago de la cuota', ahora: new Date('2026-10-30T16:30:00.000Z') })
    montarDetalle('cobranza-s-a')

    expect(await screen.findByRole('heading', { name: 'Cobranza guardada' })).toBeInTheDocument()
    expect(screen.getByText('Almacén Uno')).toBeInTheDocument()
    expect(screen.getByText('$ 100,00')).toBeInTheDocument()
    expect(screen.getByText('Efectivo: $ 100,00')).toBeInTheDocument()
    expect(screen.getByText('Pago de la cuota')).toBeInTheDocument()
    expect(screen.getByText(formatearFechaHora('2026-10-30T16:30:00.000Z').trim())).toBeInTheDocument()
    expect(screen.getByText('Sin enviar')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /compartir|descargar|comprobante/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cobranzas de hoy' })).toHaveAttribute('href', '/ruta/cobranzas')
  })

  it('muestra la referencia del medio que la lleva', async () => {
    await sembrarCobranza('a')
    await baseLocal.cobranzas.update('cobranza-s-a', {
      medios: [
        { medio_pago_id: IDS_DE_PRUEBA.efectivo, importe: '30.00', referencia: null },
        { medio_pago_id: 'transf', importe: '70.00', referencia: '0042' },
      ],
      medios_nombres: [
        { medio_pago_id: IDS_DE_PRUEBA.efectivo, nombre: 'Efectivo' },
        { medio_pago_id: 'transf', nombre: 'Transferencia' },
      ],
    })
    montarDetalle('cobranza-s-a')

    expect(await screen.findByText('Efectivo: $ 30,00')).toBeInTheDocument()
    expect(screen.getByText('Transferencia: $ 70,00 · Referencia 0042')).toBeInTheDocument()
  })

  it('una cobranza con observaciones (MEDIO_INACTIVO sobre «Billetera») dice «Con observaciones» y el texto traducido (SYN-07)', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'CON_OBSERVACIONES', { observaciones: [obs('MEDIO_INACTIVO', { nombre: 'Billetera' })] })
    montarDetalle('cobranza-s-a')

    expect(await screen.findByText('Con observaciones')).toBeInTheDocument()
    expect(await screen.findByText('El medio Billetera estaba dado de baja cuando llegó el cobro.')).toBeInTheDocument()
  })

  it('una cobranza rechazada muestra el motivo, el código y que el teléfono ya no la descuenta (SYN-06)', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'RECHAZADA', { error_codigo: 'COBRANZA_DUPLICADA' })
    montarDetalle('cobranza-s-a')

    expect(await screen.findByText('Rechazada')).toBeInTheDocument()
    expect(await screen.findByText('El sistema ya tenía otra cobranza con el mismo identificador.')).toBeInTheDocument()
    expect(screen.getByText('COBRANZA_DUPLICADA')).toBeInTheDocument()
    expect(
      screen.getByText('El cobro no quedó registrado en el sistema y el teléfono ya no lo descuenta de la cuenta del cliente; avisá a administración.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: cobranza rechazada/i })).toBeInTheDocument()
  })

  it('un código desconocido muestra el texto general de la cobranza y el código (SYN-06)', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'RECHAZADA', { error_codigo: 'CODIGO_NUEVO' })
    montarDetalle('cobranza-s-a')

    expect(await screen.findByText('El sistema no aceptó esta cobranza.')).toBeInTheDocument()
    expect(screen.getByText('CODIGO_NUEVO')).toBeInTheDocument()
  })

  it('una cobranza «Enviada» no explica nada', async () => {
    await sembrarCobranza('a')
    await conResultado('a', 'ACEPTADA')
    montarDetalle('cobranza-s-a')

    expect(await screen.findByText('Enviada')).toBeInTheDocument()
    expect(screen.queryByText(/Observaciones|Motivo del rechazo/)).not.toBeInTheDocument()
  })

  it('una cobranza que no está en el teléfono avisa y vuelve a «Cobranzas de hoy»', async () => {
    montarDetalle('no-existe')

    expect(await screen.findByText('No encontramos esa cobranza en este teléfono.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cobranzas de hoy' })).toHaveAttribute('href', '/ruta/cobranzas')
  })

  it('el cobro de una venta no es una cobranza guardada', async () => {
    await sembrarVenta('v', { cobro: '10.00' })
    montarDetalle('cobranza-v')

    expect(await screen.findByText('No encontramos esa cobranza en este teléfono.')).toBeInTheDocument()
  })
})
