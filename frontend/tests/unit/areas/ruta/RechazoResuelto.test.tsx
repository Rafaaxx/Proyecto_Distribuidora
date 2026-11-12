import 'fake-indexeddb/auto'

import { screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CobranzaGuardadaScreen } from '../../../../src/areas/ruta/cobranzas/CobranzaGuardadaScreen'
import { CobranzasDeHoyScreen } from '../../../../src/areas/ruta/cobranzas/CobranzasDeHoyScreen'
import { SincronizacionScreen } from '../../../../src/areas/ruta/sincronizacion/SincronizacionScreen'
import { VentaGuardadaScreen } from '../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { VentasDeHoyScreen } from '../../../../src/areas/ruta/ventas/VentasDeHoyScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { seleccionarCola } from '../../../../src/sync/seleccionDeCola'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarCobranza, sembrarVenta } from '../../utils/sembrarVenta'

/**
 * Change 25, tarea 16.2 (spec `ruta/area-de-ruta`, «El teléfono muestra que administración resolvió
 * un rechazo», sus tres escenarios; `design.md` D8; cita SYN-09, INV-06): «Resuelta por
 * administración» junto a «Rechazada» en «Ventas de hoy», «Cobranzas de hoy», los detalles y
 * «Sincronización», sin señal y tras recargar; no se reenvía; «Anular» no se ofrece.
 */
const RESUELTA = 'Resuelta por administración'

async function rechazarVenta(sufijo: string) {
  await baseLocal.ventas.update(`venta-${sufijo}`, { estado_envio: 'RECHAZADA' })
  const comando = await baseLocal.cola.where('operation_id').equals(`op-${sufijo}`).first()
  await baseLocal.cola.update(comando?.secuencia as number, { estado: 'RECHAZADO', error_codigo: 'JORNADA_INEXISTENTE' })
}

async function rechazarCobranza(sufijo: string) {
  await baseLocal.cobranzas.update(`cobranza-s-${sufijo}`, { estado_envio: 'RECHAZADA' })
  const comando = await baseLocal.cola.where('operation_id').equals(`op-cob-${sufijo}`).first()
  await baseLocal.cola.update(comando?.secuencia as number, { estado: 'RECHAZADO', error_codigo: 'CLIENTE_INEXISTENTE' })
}

async function sembrarTodo(resueltos: string[]) {
  await Promise.all(baseLocal.tables.map((t) => t.clear()))
  await aplicarBootstrap(
    bootstrapParaVender((b) => {
      b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
      b.rechazos_resueltos = resueltos
    }),
  )
  await sembrarVenta('a', { cajas: 1, unidades: 0, ahora: new Date('2026-10-30T11:00:00.000Z') })
  await sembrarVenta('b', { cajas: 1, unidades: 0, ahora: new Date('2026-10-30T12:00:00.000Z') })
  await sembrarCobranza('x', { ahora: new Date('2026-10-30T13:00:00.000Z') })
  await sembrarCobranza('y', { ahora: new Date('2026-10-30T14:00:00.000Z') })
  await rechazarVenta('a')
  await rechazarVenta('b')
  await rechazarCobranza('x')
  await rechazarCobranza('y')
}

function montarDetalleDeVenta(id: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/ventas/${id}` },
  )
}

describe('«Resuelta por administración» en el teléfono (tarea 16.2)', () => {
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    await sembrarTodo(['op-a', 'op-cob-x'])
  })

  it('«Ventas de hoy»: la rechazada resuelta lo dice y la pendiente no', async () => {
    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    const filas = await screen.findAllByRole('listitem')
    const resuelta = filas.find((f) => within(f).queryByText('0001-000008')) as HTMLElement
    const pendiente = filas.find((f) => within(f).queryByText('0001-000009')) as HTMLElement
    expect(await within(resuelta).findByText(RESUELTA)).toBeInTheDocument()
    expect(within(resuelta).getByText('Rechazada')).toBeInTheDocument()
    expect(within(pendiente).getByText('Rechazada')).toBeInTheDocument()
    expect(within(pendiente).queryByText(RESUELTA)).not.toBeInTheDocument()
  })

  it('«Cobranzas de hoy»: la cobranza rechazada resuelta lo dice y la otra no', async () => {
    montarEnRuta(<CobranzasDeHoyScreen />, { ruta: '/ruta/cobranzas' })

    expect(await screen.findAllByText(RESUELTA)).toHaveLength(1)
    expect(screen.getAllByText('Rechazada')).toHaveLength(2)
  })

  it('detalle de la venta: dice «Resuelta por administración» y no ofrece «Anular venta»', async () => {
    montarDetalleDeVenta('venta-a')

    expect(await screen.findByText(RESUELTA)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })

  it('detalle de la venta pendiente: no lo dice', async () => {
    montarDetalleDeVenta('venta-b')

    expect(await screen.findByText('Rechazada')).toBeInTheDocument()
    expect(screen.queryByText(RESUELTA)).not.toBeInTheDocument()
  })

  it('detalle de la cobranza resuelta', async () => {
    montarEnRuta(
      <Routes>
        <Route path="/ruta/cobranzas/:id" element={<CobranzaGuardadaScreen />} />
      </Routes>,
      { ruta: '/ruta/cobranzas/cobranza-s-x' },
    )

    expect(await screen.findByText(RESUELTA)).toBeInTheDocument()
  })

  it('«Sincronización»: la venta y la cobranza resueltas lo dicen; las pendientes no', async () => {
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await waitFor(() => expect(screen.getAllByText(RESUELTA)).toHaveLength(2))
    expect(screen.getAllByText('Rechazada')).toHaveLength(4)
  })

  it('tras recargar la aplicación sin señal (se vuelve a montar) la marca sigue ahí (ADR-062)', async () => {
    const primera = montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })
    expect(await screen.findByText(RESUELTA)).toBeInTheDocument()
    primera.unmount()

    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })
    expect(await screen.findByText(RESUELTA)).toBeInTheDocument()
  })

  it('no se reenvía: la cola a enviar no incluye ninguna rechazada, resuelta o no (SYN-09, INV-06)', async () => {
    const sesion = await baseLocal.sesion.get('actual')

    expect(await seleccionarCola(sesion?.usuario.id as string, 'disp-1')).toEqual([])
    const rechazados = await baseLocal.cola.where('estado').equals('RECHAZADO').toArray()
    expect(rechazados.map((c) => c.operation_id).sort()).toEqual(['op-a', 'op-b', 'op-cob-x', 'op-cob-y'])
  })

  it('al aplicar otro bootstrap con más rechazos resueltos, las dos ventas lo muestran', async () => {
    await aplicarBootstrap(
      bootstrapParaVender((b) => {
        b.sesion.permisos = ['VENDER', 'REGISTRAR_COBRANZA']
        b.rechazos_resueltos = ['op-a', 'op-b']
      }),
    )
    montarEnRuta(<VentasDeHoyScreen />, { ruta: '/ruta/ventas' })

    await waitFor(() => expect(screen.getAllByText(RESUELTA)).toHaveLength(2))
  })
})
