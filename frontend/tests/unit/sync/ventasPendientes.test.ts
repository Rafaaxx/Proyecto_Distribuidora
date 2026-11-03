import 'fake-indexeddb/auto'

import { beforeEach, describe, expect, it } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../src/sync/aplicarBootstrap'
import { anularVentaLocal } from '../../../src/sync/anularVentaLocal'
import {
  avisoDeCierreConPendientes,
  avisoDePendientesDeOtro,
  contarPendientes,
  contarVentasSinEnviar,
  pendientesDeOtrosUsuarios,
} from '../../../src/sync/ventasPendientes'
import { bootstrapParaVender, IDS_DE_PRUEBA } from '../utils/datosParaVender'
import { sembrarVenta } from '../utils/sembrarVenta'

/**
 * Change 22d, tarea 12.2 (spec `ruta/area-de-ruta`, escenario «Pendientes»; `design.md` D10;
 * cita SYN-09, SEG-03): lo pendiente cuenta ventas y anulaciones por separado; el aviso de
 * cierre de sesión y el de pendientes de otro nombran también las anulaciones.
 */
const YO = '00000000-0000-4000-8000-000000000001'

async function anular(sufijo: string, usuarioId = YO) {
  return anularVentaLocal({
    ventaId: `venta-${sufijo}`,
    motivo: { id: IDS_DE_PRUEBA.motivo, nombre: 'Error de carga' },
    observacion: null,
    devuelveDinero: null,
    operationId: `op-anul-${sufijo}`,
    usuarioId,
    dispositivoId: 'disp-1',
    ahora: new Date('2026-11-03T12:30:00.000Z'),
    appVersion: '1.0.0',
  })
}

describe('pendientes de envío: ventas y anulaciones (tarea 12.2)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await aplicarBootstrap(bootstrapParaVender())
  })

  it('dos ventas y una anulación: 2 y 1, y las ventas no incluyen la anulación', async () => {
    await sembrarVenta('a')
    await sembrarVenta('b', { cajas: 0, unidades: 2 })
    await anular('a')

    expect(await contarPendientes(YO)).toEqual({ ventas: 2, anulaciones: 1 })
    expect(await contarVentasSinEnviar(YO)).toBe(2)
  })

  it('una anulación ya enviada deja de contar y otra sigue', async () => {
    await sembrarVenta('a')
    await sembrarVenta('b', { cajas: 0, unidades: 2 })
    const r = await anular('a')
    await anular('b')
    await baseLocal.cola.update(r.comando.secuencia, { estado: 'ACEPTADO' })

    expect(await contarPendientes(YO)).toEqual({ ventas: 2, anulaciones: 1 })
  })

  it('no cuenta lo de otro usuario', async () => {
    await sembrarVenta('a')
    await anular('a')

    expect(await contarPendientes('otro')).toEqual({ ventas: 0, anulaciones: 0 })
  })

  it('los pendientes de otro nombran al vendedor también por la anulación', async () => {
    await sembrarVenta('a')
    await anular('a')
    const nombre = (await baseLocal.ventas.get('venta-a'))?.nota?.vendedor_nombre

    const otros = await pendientesDeOtrosUsuarios('otro')

    expect(otros).toEqual([{ vendedor: nombre, ventas: 1, anulaciones: 1 }])
  })
})

describe('avisos de pendientes (D10, D16)', () => {
  it('cierre de sesión: solo ventas queda como hasta ahora', () => {
    expect(avisoDeCierreConPendientes({ ventas: 1, anulaciones: 0 })).toBe(
      'Tenés 1 venta sin enviar. Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos.',
    )
    expect(avisoDeCierreConPendientes({ ventas: 3, anulaciones: 0 })).toBe(
      'Tenés 3 ventas sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.',
    )
  })

  it('cierre de sesión: ventas y anulaciones, y solo anulaciones', () => {
    expect(avisoDeCierreConPendientes({ ventas: 2, anulaciones: 1 })).toBe(
      'Tenés 2 ventas y 1 anulación sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.',
    )
    expect(avisoDeCierreConPendientes({ ventas: 0, anulaciones: 1 })).toBe(
      'Tenés 1 anulación sin enviar. Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos.',
    )
    expect(avisoDeCierreConPendientes({ ventas: 0, anulaciones: 2 })).toBe(
      'Tenés 2 anulaciones sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.',
    )
  })

  it('pendientes de otro: nombra al vendedor por ventas y por anulaciones', () => {
    expect(avisoDePendientesDeOtro({ vendedor: 'Ana', ventas: 1, anulaciones: 0 })).toBe(
      'Hay 1 venta sin enviar de Ana. Queda guardada en el teléfono.',
    )
    expect(avisoDePendientesDeOtro({ vendedor: 'Ana', ventas: 2, anulaciones: 1 })).toBe(
      'Hay 2 ventas y 1 anulación sin enviar de Ana. Quedan guardadas en el teléfono.',
    )
    expect(avisoDePendientesDeOtro({ vendedor: 'Ana', ventas: 0, anulaciones: 1 })).toBe(
      'Hay 1 anulación sin enviar de Ana. Queda guardada en el teléfono.',
    )
  })
})
