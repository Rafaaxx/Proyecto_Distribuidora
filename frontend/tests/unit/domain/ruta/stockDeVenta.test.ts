/**
 * Change 22a, tarea 8.1: el stock insuficiente bloquea salvo con PERMITIR_STOCK_NEGATIVO (spec
 * `ventas/venta-en-ruta`; D6 = C; STK-05, STK-06, SYN-05, INV-04).
 */
import { describe, expect, it } from 'vitest'

import { evaluarStockDeVenta, type LineaParaStock } from '../../../../src/domain/ruta/stockDeVenta'

const linea = (productoId: string, cantidadBase: number): LineaParaStock => ({ lineaId: `l-${productoId}`, productoId, cantidadBase })
const DISPONIBLE = new Map([['vino', 48]])
const SIN_PERMISO = ['VENDER']
const CON_PERMISO = ['VENDER', 'PERMITIR_STOCK_NEGATIVO']

describe('evaluarStockDeVenta', () => {
  it('sin el permiso, 50 con 48 disponibles bloquea con el aviso y el pedido de actualizar datos', () => {
    const r = evaluarStockDeVenta([linea('vino', 50)], DISPONIBLE, SIN_PERMISO)
    expect(r.lineas).toEqual([
      { lineaId: 'l-vino', productoId: 'vino', disponible: 48, aviso: 'Supera el stock del vehículo (quedan 48)' },
    ])
    expect(r.confirmacion).toBe('bloqueada')
    expect(r.mensaje).toMatch(/actualiz/i)
    expect(r.mensaje).toMatch(/señal/i)
  })

  it('con el permiso, el mismo aviso y pide "Vender igual"', () => {
    const r = evaluarStockDeVenta([linea('vino', 50)], DISPONIBLE, CON_PERMISO)
    expect(r.lineas[0]?.aviso).toBe('Supera el stock del vehículo (quedan 48)')
    expect(r.confirmacion).toBe('vender-igual')
    expect(r.mensaje).toBeNull()
  })

  it('sin exceso (exactamente lo disponible) no hay aviso ni bloqueo en ninguno de los dos casos', () => {
    for (const permisos of [SIN_PERMISO, CON_PERMISO]) {
      const r = evaluarStockDeVenta([linea('vino', 48)], DISPONIBLE, permisos)
      expect(r).toEqual({ lineas: [], confirmacion: 'libre', mensaje: null })
    }
  })

  it('suma las líneas del mismo producto en unidad base (2 cajas x6 + 3 botellas = 15)', () => {
    const r = evaluarStockDeVenta([linea('vino', 12), linea('vino', 3)], new Map([['vino', 14]]), SIN_PERMISO)
    expect(r.confirmacion).toBe('bloqueada')
    expect(r.lineas.map((l) => l.aviso)).toEqual([
      'Supera el stock del vehículo (quedan 14)',
      'Supera el stock del vehículo (quedan 14)',
    ])
  })

  it('un producto sin stock informa quedan 0; con stock negativo también 0', () => {
    expect(evaluarStockDeVenta([linea('x', 1)], new Map(), SIN_PERMISO).lineas[0]?.aviso).toBe(
      'Supera el stock del vehículo (quedan 0)',
    )
    expect(evaluarStockDeVenta([linea('vino', 1)], new Map([['vino', -2]]), CON_PERMISO).lineas[0]?.aviso).toBe(
      'Supera el stock del vehículo (quedan 0)',
    )
  })

  it('solo marca el producto que excede y deja pasar a los demás', () => {
    const r = evaluarStockDeVenta(
      [linea('vino', 50), linea('agua', 2)],
      new Map([['vino', 48], ['agua', 10]]),
      CON_PERMISO,
    )
    expect(r.lineas.map((l) => l.productoId)).toEqual(['vino'])
  })
})
