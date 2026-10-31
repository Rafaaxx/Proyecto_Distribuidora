import 'fake-indexeddb/auto'

import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { VentasDeHoyScreen } from '../../../../../src/areas/ruta/ventas/VentasDeHoyScreen'
import { baseLocal } from '../../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../../src/sync/aplicarBootstrap'
import { bootstrapParaVender } from '../../../utils/datosParaVender'
import { ID, clienteDePrueba } from '../../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../../utils/rutaDePrueba'
import { sembrarVenta } from '../../../utils/sembrarVenta'

/**
 * Change 22a, tarea 11.1 (spec `ruta/area-de-ruta`, "Ventas de hoy desde la base local";
 * `design.md` D14; cita SYN-09, RUT-04): lista las ventas de la jornada abierta con número,
 * cliente, total y estado de envío, sin señal; las de otra jornada no aparecen; el detalle abre
 * la nota.
 */
describe('VentasDeHoyScreen (tarea 11.1)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.clientes = [
          { ...clienteDePrueba(1, 'Almacén Uno'), credito: { limite: null, politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null } },
          { ...clienteDePrueba(2, 'Kiosco Dos'), credito: { limite: null, politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null } },
        ]
      }),
    )
  })

  it('sin señal lista las ventas con número, cliente, total y "Sin enviar"', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0, ahora: new Date('2026-10-30T14:00:00.000Z') })
    await sembrarVenta('b', { clienteId: ID(102), cajas: 0, unidades: 2, ahora: new Date('2026-10-30T15:00:00.000Z') })

    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    const filas = await screen.findAllByRole('listitem')
    expect(filas).toHaveLength(2)
    // La más nueva primero.
    expect(within(filas[0] as HTMLElement).getByText('0001-000009')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText('Kiosco Dos')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText('$ 16.000,00')).toBeInTheDocument()
    expect(within(filas[0] as HTMLElement).getByText('Sin enviar')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('0001-000008')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('Almacén Uno')).toBeInTheDocument()
    expect(within(filas[1] as HTMLElement).getByText('$ 48.000,00')).toBeInTheDocument()
  })

  it('las ventas de otra jornada no aparecen (RUT-04)', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 0, unidades: 2 })
    await baseLocal.ventas.update('venta-b', { jornada_id: 'jornada-anterior' })

    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    expect(await screen.findByText('0001-000008')).toBeInTheDocument()
    expect(screen.queryByText('0001-000009')).not.toBeInTheDocument()
  })

  it('cada venta enlaza a su detalle con la nota', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })

    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    expect(await screen.findByRole('link', { name: /0001-000008/ })).toHaveAttribute('href', '/ruta/ventas/venta-a')
  })

  it('sin ventas en la jornada lo dice', async () => {
    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    expect(await screen.findByText('Todavía no hiciste ventas en esta jornada.')).toBeInTheDocument()
  })

  it('sin datos descargados lo avisa', async () => {
    await baseLocal.sesion.clear()

    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    expect(await screen.findByText(/todavía no hay datos descargados/i)).toBeInTheDocument()
  })
})
