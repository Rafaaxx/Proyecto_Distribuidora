import { describe, expect, it } from 'vitest'

import { aProductoConPrecio, armarPedido, type ItemDelPedido, type ProductoConPrecio } from '../../../../src/domain/ventas/pedido'

const BOTELLA = { presentacionId: 'p-botella', nombre: 'Botella', unidadesBase: 1, esReferencia: false }
const CAJA_X6 = { presentacionId: 'p-caja', nombre: 'Caja x6', unidadesBase: 6, esReferencia: true }

const VINO_A: ProductoConPrecio = {
  productoId: 'vino-a',
  nombre: 'Vino A',
  precioReferencia: '12500.00',
  unidadesReferencia: 6,
  stockBase: 48,
  listaVersionId: 'v2',
  presentaciones: [BOTELLA, CAJA_X6],
}
const SIDRA_SIN_PRECIO: ProductoConPrecio = {
  productoId: 'sidra',
  nombre: 'Sidra',
  precioReferencia: null,
  unidadesReferencia: null,
  stockBase: 10,
  listaVersionId: 'v2',
  presentaciones: [BOTELLA],
}

const idDeLinea = (productoId: string, presentacionId: string) => `linea-${productoId}-${presentacionId}`
const productos = (...lista: ProductoConPrecio[]) => new Map(lista.map((p) => [p.productoId, p]))

/** VTA-02, PRC-22, VTA-10: del pedido (cajas + unidades) a las líneas que se envían. */
describe('armarPedido (VTA-02, PRC-22, design D7, D8)', () => {
  it('2 cajas + 3 unidades de Vino A: dos líneas con brutos 25000.00 y 6250.00 y total 31250.00', () => {
    const items: ItemDelPedido[] = [{ productoId: 'vino-a', cajas: 2, unidades: 3 }]
    const pedido = armarPedido(items, productos(VINO_A), idDeLinea)
    expect(pedido.lineas.map((l) => [l.lineaId, l.presentacionId, l.cantidad, l.importeBruto, l.listaVersionId])).toEqual([
      ['linea-vino-a-p-caja', 'p-caja', 2, '25000.00', 'v2'],
      ['linea-vino-a-p-botella', 'p-botella', 3, '6250.00', 'v2'],
    ])
    expect(pedido.total.toFixed(2)).toBe('31250.00')
    expect(pedido.completo).toBe(true)
    expect(pedido.visibles.map((v) => v.presentacionNombre)).toEqual(['Caja x6', 'Botella'])
  })

  it('un producto sin precio en la lista no entra a las líneas y bloquea el pedido (VTA-10)', () => {
    const items: ItemDelPedido[] = [
      { productoId: 'vino-a', cajas: 1, unidades: 0 },
      { productoId: 'sidra', cajas: 0, unidades: 2 },
    ]
    const pedido = armarPedido(items, productos(VINO_A, SIDRA_SIN_PRECIO), idDeLinea)
    expect(pedido.lineas).toHaveLength(1)
    expect(pedido.errores['sidra']).toMatch(/sin precio/i)
    expect(pedido.completo).toBe(false)
  })

  it('unidades sueltas en un producto sin presentación de 1 unidad es un error de ese producto (CAT-07)', () => {
    const sinUnidad: ProductoConPrecio = { ...VINO_A, presentaciones: [CAJA_X6] }
    const pedido = armarPedido([{ productoId: 'vino-a', cajas: 0, unidades: 2 }], productos(sinUnidad), idDeLinea)
    expect(pedido.errores['vino-a']).toMatch(/unidades sueltas/i)
    expect(pedido.completo).toBe(false)
  })

  it('un producto cuyos datos todavía no llegaron deja el pedido incompleto sin marcar error', () => {
    const pedido = armarPedido([{ productoId: 'vino-a', cajas: 1, unidades: 0 }], new Map(), idDeLinea)
    expect(pedido.pendientes).toEqual(['vino-a'])
    expect(pedido.errores).toEqual({})
    expect(pedido.completo).toBe(false)
  })

  it('un item en cero no genera línea y un pedido sin líneas no está completo', () => {
    const pedido = armarPedido([{ productoId: 'vino-a', cajas: 0, unidades: 0 }], productos(VINO_A), idDeLinea)
    expect(pedido.lineas).toEqual([])
    expect(pedido.completo).toBe(false)
    expect(pedido.total.toFixed(2)).toBe('0.00')
  })

  it('marca el producto que supera el stock de la ubicación sin bloquear (STK-05, el permiso lo decide el servidor)', () => {
    const pedido = armarPedido([{ productoId: 'vino-a', cajas: 9, unidades: 0 }], productos(VINO_A), idDeLinea)
    expect(pedido.superaStock).toEqual(['vino-a'])
    expect(pedido.completo).toBe(true)
    const justo = armarPedido([{ productoId: 'vino-a', cajas: 8, unidades: 0 }], productos(VINO_A), idDeLinea)
    expect(justo.superaStock).toEqual([])
  })

  it('el mismo identificador de línea se conserva entre dos armados (reintento con la misma operación, INV-06)', () => {
    const items: ItemDelPedido[] = [{ productoId: 'vino-a', cajas: 1, unidades: 0 }]
    const primero = armarPedido(items, productos(VINO_A), idDeLinea)
    const segundo = armarPedido(items, productos(VINO_A), idDeLinea)
    expect(segundo.lineas).toEqual(primero.lineas)
  })
})

describe('aProductoConPrecio (D19)', () => {
  const RESPUESTA = {
    producto_id: 'vino-a',
    codigo: 'P-001',
    nombre: 'Vino A',
    precio_referencia: '12500.00' as string | null,
    unidades_referencia: 6 as number | null,
    sin_precio: false,
    stock_base: 48 as number | null,
    presentaciones: [
      { presentacion_id: 'p-botella', nombre: 'Botella', unidades_base: 1, es_referencia: false },
      { presentacion_id: 'p-caja', nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
    ],
  }

  it('pasa la respuesta del servidor al producto del pedido, con la versión de la que sale el precio', () => {
    expect(aProductoConPrecio(RESPUESTA, 'v2')).toEqual(VINO_A)
  })

  it('un producto sin precio conserva el precio nulo y sigue siendo un producto del pedido', () => {
    const sin = aProductoConPrecio({ ...RESPUESTA, precio_referencia: null, unidades_referencia: null, sin_precio: true, stock_base: null }, 'v2')
    expect(sin.precioReferencia).toBeNull()
    expect(sin.stockBase).toBeNull()
  })
})
