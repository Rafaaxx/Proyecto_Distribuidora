import 'fake-indexeddb/auto'

import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapParaVender } from '../../utils/datosParaVender'
import { ID } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarVenta } from '../../utils/sembrarVenta'
import { sincronizadorDePrueba } from '../../utils/sincronizadorDePrueba'

import { SincronizacionScreen } from '../../../../src/areas/ruta/sincronizacion/SincronizacionScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { formatearFechaHora } from '../../../../src/lib/fecha'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { iniciarDisparadores, type Disparadores } from '../../../../src/sync/disparadores'
import {
  CLAVE_ULTIMA_SINCRONIZACION,
  CLAVE_ULTIMO_ERROR_SYNC,
} from '../../../../src/sync/sincronizar'

/**
 * Change 22b, tarea 10.2 (spec `ruta/area-de-ruta`, «La pantalla de sincronización muestra lo
 * pendiente y lo que volvió con problemas»; `design.md` D8; cita SYN-04, SYN-06, `02` §12.3).
 */
const TEXTO_DE_RECHAZADA = 'El sistema no aceptó esta venta. Sigue guardada en el teléfono; avisá a administración.'

async function ventaConResultado(
  sufijo: string,
  secuencia: number,
  estadoVenta: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
  estadoComando: 'ACEPTADO' | 'ACEPTADO_CON_OBSERVACIONES' | 'RECHAZADO',
  codigo: string | null = null,
) {
  await sembrarVenta(sufijo, { cajas: 1, unidades: 0, ahora: new Date(`2026-10-30T1${secuencia}:00:00.000Z`) })
  await baseLocal.ventas.update(`venta-${sufijo}`, { estado_envio: estadoVenta })
  const comando = await baseLocal.cola.where('operation_id').equals(`op-${sufijo}`).first()
  await baseLocal.cola.update(comando?.secuencia as number, { estado: estadoComando, error_codigo: codigo })
}

describe('SincronizacionScreen (tarea 10.2)', () => {
  let activos: Disparadores | null = null
  beforeEach(async () => {
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true)
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })
  afterEach(() => {
    activos?.detener()
    activos = null
    vi.restoreAllMocks()
  })

  it('lista las «Con observaciones» y las «Rechazadas» con número, cliente, total, estado y, en la rechazada, el código y el texto', async () => {
    await ventaConResultado('a', 2, 'ACEPTADA', 'ACEPTADO')
    await ventaConResultado('b', 3, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES')
    await ventaConResultado('c', 4, 'RECHAZADA', 'RECHAZADO', 'JORNADA_INEXISTENTE')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByRole('heading', { name: 'Sincronización' })).toBeInTheDocument()
    const filas = await screen.findAllByRole('listitem')
    expect(filas).toHaveLength(2)

    const conObservaciones = filas.find((f) => within(f).queryByText('0001-000009')) as HTMLElement
    expect(within(conObservaciones).getByText('Con observaciones')).toBeInTheDocument()
    expect(within(conObservaciones).getByText('Almacén Uno')).toBeInTheDocument()
    expect(within(conObservaciones).getByText('$ 48.000,00')).toBeInTheDocument()

    const rechazada = filas.find((f) => within(f).queryByText('0001-000010')) as HTMLElement
    expect(within(rechazada).getByText('Rechazada')).toBeInTheDocument()
    expect(within(rechazada).getByText('JORNADA_INEXISTENTE')).toBeInTheDocument()
    expect(within(rechazada).getByText(TEXTO_DE_RECHAZADA)).toBeInTheDocument()
    // La enviada sin problemas no se lista.
    expect(screen.queryByText('0001-000008')).not.toBeInTheDocument()
  })

  it('cada venta con problemas abre su detalle', async () => {
    await ventaConResultado('c', 4, 'RECHAZADA', 'RECHAZADO', 'JORNADA_INEXISTENTE')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const enlace = await screen.findByRole('link', { name: /0001-000008/ })
    expect(enlace).toHaveAttribute('href', '/ruta/ventas/venta-c')
  })

  it('con todo enviado dice «Todo enviado», la hora de la última sincronización y la lista vacía', async () => {
    await ventaConResultado('a', 2, 'ACEPTADA', 'ACEPTADO')
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SINCRONIZACION, valor: '2026-11-01T12:34:00.000Z' })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('Todo enviado')).toBeInTheDocument()
    expect(await screen.findByText(`Última sincronización: ${formatearFechaHora('2026-11-01T12:34:00.000Z')}`)).toBeInTheDocument()
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('muestra los pendientes, la conexión y el botón «Sincronizar»', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('2 ventas sin enviar')).toBeInTheDocument()
    expect(screen.getByText('Con conexión')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })

  it('una sesión vencida pide iniciar sesión con señal', async () => {
    await baseLocal.meta.put({
      clave: CLAVE_ULTIMO_ERROR_SYNC,
      valor: JSON.stringify({ tipo: 'sesion_vencida', codigo: null, en: '2026-11-01T12:00:00.000Z' }),
    })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('Iniciá sesión con señal para enviar las ventas')).toBeInTheDocument()
  })

  it('un error del pedido dice «No se pudo enviar» con su código', async () => {
    await baseLocal.meta.put({
      clave: CLAVE_ULTIMO_ERROR_SYNC,
      valor: JSON.stringify({ tipo: 'error_pedido', codigo: 'VALIDACION_FALLIDA', en: '2026-11-01T12:00:00.000Z' }),
    })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('No se pudo enviar')).toBeInTheDocument()
    expect(screen.getByText('VALIDACION_FALLIDA')).toBeInTheDocument()
  })

  it('el botón «Sincronizar» dispara a pedido y muestra «Enviando…» mientras tanto', async () => {
    const prueba = sincronizadorDePrueba()
    activos = iniciarDisparadores({ usuarioId: ID(1), dispositivoId: 'd1', sincronizador: prueba.sincronizador })
    let terminar: () => void = () => undefined
    prueba.responderCon(
      () =>
        new Promise((resolver) => {
          terminar = () => resolver({ tipo: 'completa', enviadas: 0 })
        }),
    )
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Sincronizar' }))
    expect(await screen.findByRole('button', { name: 'Enviando…' })).toBeDisabled()
    expect(prueba.origenes).toContain('manual')
    await act(async () => terminar())
    expect(await screen.findByRole('button', { name: 'Sincronizar' })).toBeEnabled()
  })
})
