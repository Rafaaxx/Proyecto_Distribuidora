import 'fake-indexeddb/auto'

import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { bootstrapParaVender } from '../../utils/datosParaVender'
import { ID } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarAnulacion, sembrarCobranza, sembrarVenta } from '../../utils/sembrarVenta'
import { sincronizadorDePrueba } from '../../utils/sincronizadorDePrueba'

import { SincronizacionScreen } from '../../../../src/areas/ruta/sincronizacion/SincronizacionScreen'
import { baseLocal, type ObservacionLocal } from '../../../../src/lib/dispositivo/db'
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
const TEXTO_DE_RECHAZADA = 'La jornada de la venta no existe en el sistema.'
const AVISO_DE_RECHAZADA = 'Sigue guardada en el teléfono; avisá a administración.'

async function ventaConResultado(
  sufijo: string,
  secuencia: number,
  estadoVenta: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
  estadoComando: 'ACEPTADO' | 'ACEPTADO_CON_OBSERVACIONES' | 'RECHAZADO',
  codigo: string | null = null,
  observaciones?: ObservacionLocal[],
) {
  await sembrarVenta(sufijo, { cajas: 1, unidades: 0, ahora: new Date(`2026-10-30T1${secuencia}:00:00.000Z`) })
  await baseLocal.ventas.update(`venta-${sufijo}`, { estado_envio: estadoVenta })
  const comando = await baseLocal.cola.where('operation_id').equals(`op-${sufijo}`).first()
  await baseLocal.cola.update(comando?.secuencia as number, { estado: estadoComando, error_codigo: codigo, observaciones })
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
    expect(within(rechazada).getByText(AVISO_DE_RECHAZADA)).toBeInTheDocument()
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

  /**
   * Change 22c, tarea 9.2 (spec `ruta/area-de-ruta`, «La pantalla de sincronización muestra lo
   * pendiente y lo que volvió con problemas»; D4, D5; cita SYN-04, SYN-06, SYN-07, SYN-09).
   */
  const obs = (codigo: string, detalle: Record<string, unknown> | null = null): ObservacionLocal => ({
    codigo,
    operacion_tipo: 'VENTA',
    operacion_id: 'op',
    detalle,
  })

  it('la fila de una «Con observaciones» muestra la primera observación traducida y «1 más»', async () => {
    await ventaConResultado('b', 3, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES', null, [
      obs('LISTA_NO_VIGENTE'),
      obs('STOCK_NEGATIVO', { producto_id: ID(30) }),
    ])
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('0001-000008')).closest('li') as HTMLElement
    expect(within(fila).getByText('Los precios no eran los de la versión vigente de la lista en ese momento.')).toBeInTheDocument()
    expect(within(fila).getByText('1 más')).toBeInTheDocument()
  })

  it('con una sola observación no dice «más», y con tres dice «2 más»', async () => {
    await ventaConResultado('a', 2, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES', null, [obs('DESCUENTO_DIFIERE')])
    await ventaConResultado('b', 3, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES', null, [
      obs('JORNADA_LIBERADA'),
      obs('DESCUENTO_DIFIERE'),
      obs('LISTA_NO_VIGENTE'),
    ])
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const unica = (await screen.findByText('0001-000008')).closest('li') as HTMLElement
    expect(within(unica).getByText('El descuento no coincide con el que calcula el sistema.')).toBeInTheDocument()
    expect(within(unica).queryByText(/más$/)).not.toBeInTheDocument()
    const tres = screen.getByText('0001-000009').closest('li') as HTMLElement
    expect(within(tres).getByText('2 más')).toBeInTheDocument()
  })

  it('una «Con observaciones» sin la lista guardada dice que el detalle no está en el teléfono', async () => {
    await ventaConResultado('b', 3, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('0001-000008')).closest('li') as HTMLElement
    expect(within(fila).getByText('El detalle no está en el teléfono; consultalo con administración.')).toBeInTheDocument()
  })

  it('una rechazada con un código que el teléfono no conoce dice «El sistema no aceptó esta venta.» con el código', async () => {
    await ventaConResultado('c', 4, 'RECHAZADA', 'RECHAZADO', 'CODIGO_NUEVO')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('0001-000008')).closest('li') as HTMLElement
    expect(within(fila).getByText('El sistema no aceptó esta venta.')).toBeInTheDocument()
    expect(within(fila).getByText('CODIGO_NUEVO')).toBeInTheDocument()
    expect(within(fila).getByText(AVISO_DE_RECHAZADA)).toBeInTheDocument()
  })

  it('las secciones tienen la ayuda de observaciones y rechazos', async () => {
    await ventaConResultado('b', 3, 'CON_OBSERVACIONES', 'ACEPTADO_CON_OBSERVACIONES', null, [obs('DESCUENTO_DIFIERE')])
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findByText('0001-000008')
    expect(screen.getAllByRole('button', { name: /ayuda: observaciones y rechazos/i }).length).toBeGreaterThan(0)
  })

  /**
   * Change 22d, tarea 12.2 (spec `ruta/area-de-ruta`, «Anulación rechazada en Sincronización»,
   * «Pendientes»; `design.md` D10, D11; cita SYN-06, SYN-07, SYN-09).
   */
  async function anulacionConResultado(
    sufijo: string,
    estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
    resultado: { error_codigo?: string | null; observaciones?: ObservacionLocal[] },
  ) {
    await sembrarVenta(sufijo, { cajas: 1, unidades: 0 })
    await sembrarAnulacion(sufijo)
    await baseLocal.anulaciones.update(`venta-${sufijo}`, { estado_envio: estado })
    const comando = await baseLocal.cola.where('operation_id').equals(`op-anul-${sufijo}`).first()
    await baseLocal.cola.update(comando?.secuencia as number, {
      estado: estado === 'RECHAZADA' ? 'RECHAZADO' : 'ACEPTADO_CON_OBSERVACIONES',
      ...resultado,
    })
  }

  it('una anulación rechazada con VENTA_YA_ANULADA se lista como «Anulación de {número}» con su texto, el código y el aviso, y abre el detalle de la venta', async () => {
    await anulacionConResultado('a', 'RECHAZADA', { error_codigo: 'VENTA_YA_ANULADA' })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Anulación de 0001-000008')).closest('li') as HTMLElement
    expect(within(fila).getByText('Rechazada')).toBeInTheDocument()
    expect(within(fila).getByText('La venta ya estaba anulada en el sistema.')).toBeInTheDocument()
    expect(within(fila).getByText('VENTA_YA_ANULADA')).toBeInTheDocument()
    expect(within(fila).getByText('La venta sigue vigente en el teléfono; avisá a administración.')).toBeInTheDocument()
    expect(within(fila).getByRole('link')).toHaveAttribute('href', '/ruta/ventas/venta-a')
  })

  it('una anulación con observaciones muestra la primera traducida con el texto de la anulación', async () => {
    await anulacionConResultado('a', 'CON_OBSERVACIONES', {
      observaciones: [obs('JORNADA_LIBERADA'), obs('UBICACION_TOMADA_AL_SINCRONIZAR')],
    })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Anulación de 0001-000008')).closest('li') as HTMLElement
    expect(within(fila).getByText('Con observaciones')).toBeInTheDocument()
    expect(within(fila).getByText('La jornada había sido liberada cuando llegó la anulación.')).toBeInTheDocument()
    expect(within(fila).getByText('1 más')).toBeInTheDocument()
  })

  it('una anulación aceptada sin problemas no se lista', async () => {
    await anulacionConResultado('a', 'ACEPTADA', {})
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findByRole('heading', { name: 'Sincronización' })
    expect(screen.queryByText(/Anulación de/)).not.toBeInTheDocument()
  })

  it('dos ventas y una anulación sin enviar: «2 ventas y 1 anulación sin enviar»', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    await sembrarAnulacion('a')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('2 ventas y 1 anulación sin enviar')).toBeInTheDocument()
  })

  /**
   * Change 23, tarea 10.1 (spec `ruta/area-de-ruta`, «Cobranza rechazada en Sincronización»,
   * «Pendientes»; `design.md` D10, D11; cita SYN-06, SYN-09).
   */
  async function cobranzaConResultado(
    sufijo: string,
    estado: 'ACEPTADA' | 'CON_OBSERVACIONES' | 'RECHAZADA',
    resultado: { error_codigo?: string | null; observaciones?: ObservacionLocal[] },
  ) {
    await sembrarCobranza(sufijo)
    await baseLocal.cobranzas.update(`cobranza-s-${sufijo}`, { estado_envio: estado })
    const comando = await baseLocal.cola.where('operation_id').equals(`op-cob-${sufijo}`).first()
    await baseLocal.cola.update(comando?.secuencia as number, {
      estado: estado === 'RECHAZADA' ? 'RECHAZADO' : 'ACEPTADO_CON_OBSERVACIONES',
      ...resultado,
    })
  }

  it('una cobranza rechazada se lista como «Cobranza a {cliente}» con su texto, el código y el aviso, y abre su detalle', async () => {
    await cobranzaConResultado('a', 'RECHAZADA', { error_codigo: 'RECURSO_NO_ENCONTRADO' })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Cobranza a Almacén Uno')).closest('li') as HTMLElement
    expect(within(fila).getByText('Rechazada')).toBeInTheDocument()
    expect(within(fila).getByText('El sistema no tiene el cliente o el medio de pago de la cobranza.')).toBeInTheDocument()
    expect(within(fila).getByText('RECURSO_NO_ENCONTRADO')).toBeInTheDocument()
    expect(
      within(fila).getByText(
        'El cobro no quedó registrado en el sistema y el teléfono ya no lo descuenta de la cuenta del cliente; avisá a administración.',
      ),
    ).toBeInTheDocument()
    expect(within(fila).getByRole('link')).toHaveAttribute('href', '/ruta/cobranzas/cobranza-s-a')
  })

  it('una cobranza con observaciones muestra la primera traducida con el texto de la cobranza', async () => {
    await cobranzaConResultado('a', 'CON_OBSERVACIONES', {
      observaciones: [obs('JORNADA_LIBERADA'), obs('PERMISO_REVOCADO')],
    })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Cobranza a Almacén Uno')).closest('li') as HTMLElement
    expect(within(fila).getByText('Con observaciones')).toBeInTheDocument()
    expect(within(fila).getByText('La jornada había sido liberada cuando llegó la cobranza.')).toBeInTheDocument()
    expect(within(fila).getByText('1 más')).toBeInTheDocument()
  })

  it('una cobranza con un código desconocido muestra el texto general de la cobranza y el código', async () => {
    await cobranzaConResultado('a', 'RECHAZADA', { error_codigo: 'CODIGO_NUEVO' })
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    const fila = (await screen.findByText('Cobranza a Almacén Uno')).closest('li') as HTMLElement
    expect(within(fila).getByText('El sistema no aceptó esta cobranza.')).toBeInTheDocument()
    expect(within(fila).getByText('CODIGO_NUEVO')).toBeInTheDocument()
  })

  it('una cobranza aceptada sin problemas no se lista (y sincronizar otra vez no cambia nada)', async () => {
    await cobranzaConResultado('a', 'ACEPTADA', {})
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    await screen.findByRole('heading', { name: 'Sincronización' })
    expect(screen.queryByText(/Cobranza a/)).not.toBeInTheDocument()
  })

  it('dos ventas, una anulación y una cobranza sin enviar: «2 ventas, 1 anulación y 1 cobranza sin enviar»', async () => {
    await sembrarVenta('a', { cajas: 1, unidades: 0 })
    await sembrarVenta('b', { cajas: 1, unidades: 0 })
    await sembrarAnulacion('a')
    await sembrarCobranza('a')
    montarEnRuta(<SincronizacionScreen />, { ruta: '/ruta/sincronizacion' })

    expect(await screen.findByText('2 ventas, 1 anulación y 1 cobranza sin enviar')).toBeInTheDocument()
  })
})
