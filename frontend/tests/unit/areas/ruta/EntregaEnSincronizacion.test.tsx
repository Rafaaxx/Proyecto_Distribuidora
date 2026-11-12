import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SincronizacionScreen } from '../../../../src/areas/ruta/sincronizacion/SincronizacionScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { aplicarResultados } from '../../../../src/sync/aplicarResultados'
import { terminarElDia } from '../../../../src/sync/terminarDia'
import { ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarVenta } from '../../utils/sembrarVenta'

/**
 * Change 24, tarea 15.1 (spec `ruta/area-de-ruta`, «Entrega rechazada» y «Doble sincronización de
 * la entrega»; `design.md` D10, D11; cita SYN-06, SYN-09, INV-06): «Sincronización» muestra la
 * entrega como «Entrega del día» con su estado y, si el servidor la rechazó, su texto y su código.
 */
const AHORA = new Date('2026-11-04T18:00:00.000Z')
const RESULTADO_EN = new Date('2026-11-04T18:05:00.000Z')

async function terminar() {
  return terminarElDia({ operationId: 'op-entrega', usuarioId: ID(1), dispositivoId: 'disp-1', ahora: AHORA, appVersion: '1.0.0' })
}

describe('la entrega del día en «Sincronización» (tarea 15.1)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sin entrega no aparece nada de la entrega', async () => {
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findByRole('heading', { name: 'Sincronización' })
    expect(screen.queryByText('Entrega del día')).not.toBeInTheDocument()
  })

  it('con la entrega esperando su turno dice «Entrega del día» y «Sin enviar»; no se cuenta como venta sin enviar', async () => {
    await terminar()
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Entrega del día')).closest('li') as HTMLElement
    expect(within(fila).getByText('Sin enviar')).toBeInTheDocument()
    expect(screen.getByText('Todo enviado')).toBeInTheDocument()
  })

  it('con las ventas sin enviar delante, ellas se cuentan y la entrega espera (SYN-03)', async () => {
    await sembrarVenta('a')
    await terminar()
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('1 venta sin enviar')).toBeInTheDocument()
    expect(screen.getByText('Entrega del día')).toBeInTheDocument()
  })

  it('aceptada: «Enviada» y sin texto de rechazo (SYN-09)', async () => {
    const { comando } = await terminar()
    await aplicarResultados([{ operation_id: comando.operation_id, estado: 'ACEPTADO', resultado: {}, error_codigo: null }], RESULTADO_EN)
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Entrega del día')).closest('li') as HTMLElement
    expect(within(fila).getByText('Enviada')).toBeInTheDocument()
    expect(within(fila).queryByText('Avisá a tu supervisor.')).not.toBeInTheDocument()
  })

  it.each([
    ['JORNADA_ESTADO_INVALIDO', 'La jornada ya no estaba abierta cuando llegó la entrega.'],
    ['JORNADA_YA_ENTREGADA', 'La jornada ya estaba entregada.'],
    ['PERMISO_REQUERIDO', 'La entrega llegó con datos incompletos o inválidos.'],
  ])('rechazada con %s: «Rechazada», sin el código crudo, «%s» y «Avisá a tu supervisor.» (SYN-06)', async (codigo, texto) => {
    const { comando } = await terminar()
    await aplicarResultados([{ operation_id: comando.operation_id, estado: 'RECHAZADO', resultado: null, error_codigo: codigo }], RESULTADO_EN)
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Entrega del día')).closest('li') as HTMLElement
    expect(within(fila).getByText('Rechazada')).toBeInTheDocument()
    expect(within(fila).queryByText(codigo)).not.toBeInTheDocument()
    expect(within(fila).getByText(texto)).toBeInTheDocument()
    expect(within(fila).getByText('Avisá a tu supervisor.')).toBeInTheDocument()
  })

  it('aplicar dos veces el mismo resultado no cambia lo mostrado (INV-06)', async () => {
    const { comando } = await terminar()
    const resultado = [{ operation_id: comando.operation_id, estado: 'ACEPTADO', resultado: {}, error_codigo: null }]
    await aplicarResultados(resultado, RESULTADO_EN)
    await aplicarResultados(resultado, new Date('2026-11-04T18:10:00.000Z'))
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findByText('Entrega del día')
    expect(screen.getAllByText('Entrega del día')).toHaveLength(1)
    expect(await baseLocal.cola.get(comando.secuencia)).toMatchObject({ resultado_en: RESULTADO_EN.toISOString() })
  })
})
