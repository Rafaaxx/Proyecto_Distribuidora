/**
 * Stock insuficiente en el teléfono (change 22a, `design.md` D6 = C; STK-05, STK-06, SYN-05,
 * RUT-04, INV-04). Sin `PERMITIR_STOCK_NEGATIVO` (permisos del bootstrap) la venta que supera el
 * stock del vehículo no se confirma; con el permiso se avisa y se pide "Vender igual". Puro: las
 * cantidades llegan en unidad base (enteros) y el disponible ya viene calculado (D5).
 */
export const PERMISO_STOCK_NEGATIVO = 'PERMITIR_STOCK_NEGATIVO'

export const MENSAJE_ACTUALIZAR_DATOS_POR_STOCK =
  'No se puede confirmar: actualizá los datos con señal para ver el stock del vehículo.'

export interface LineaParaStock {
  lineaId: string
  productoId: string
  /** Cantidad en unidad base. */
  cantidadBase: number
}

export interface AvisoDeStockDeLinea {
  lineaId: string
  productoId: string
  /** Lo que quedaba antes de esta venta, nunca negativo. */
  disponible: number
  aviso: string
}

export interface EvaluacionDeStock {
  /** Las líneas de los productos que superan el stock. */
  lineas: AvisoDeStockDeLinea[]
  /** `libre` = sin exceso; `vender-igual` = con permiso, falta la confirmación expresa. */
  confirmacion: 'libre' | 'bloqueada' | 'vender-igual'
  /** Solo en `bloqueada`: qué hacer. */
  mensaje: string | null
}

export function evaluarStockDeVenta(
  lineas: readonly LineaParaStock[],
  disponiblePorProducto: ReadonlyMap<string, number>,
  permisos: readonly string[],
): EvaluacionDeStock {
  const pedido = new Map<string, number>()
  for (const l of lineas) pedido.set(l.productoId, (pedido.get(l.productoId) ?? 0) + l.cantidadBase)

  const avisos: AvisoDeStockDeLinea[] = []
  for (const l of lineas) {
    const disponible = disponiblePorProducto.get(l.productoId) ?? 0
    if ((pedido.get(l.productoId) ?? 0) <= disponible) continue
    const quedan = Math.max(0, disponible)
    avisos.push({
      lineaId: l.lineaId,
      productoId: l.productoId,
      disponible: quedan,
      aviso: `Supera el stock del vehículo (quedan ${quedan})`,
    })
  }

  if (avisos.length === 0) return { lineas: [], confirmacion: 'libre', mensaje: null }
  if (permisos.includes(PERMISO_STOCK_NEGATIVO)) {
    return { lineas: avisos, confirmacion: 'vender-igual', mensaje: null }
  }
  return { lineas: avisos, confirmacion: 'bloqueada', mensaje: MENSAJE_ACTUALIZAR_DATOS_POR_STOCK }
}
