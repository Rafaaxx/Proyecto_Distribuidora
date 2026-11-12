/**
 * Del pedido que arma el usuario (por producto, cajas + unidades) a las líneas que se envían
 * (change 18a, tarea 12.2; `design.md` D2, D7, D8; VTA-02, VTA-10, PRC-22, STK-05). Lógica pura:
 * la pantalla le pasa los precios y el stock que leyó del servidor y pinta el resultado.
 */

import type { Importe } from '../../lib/money'
import { calcularBrutoDelPedido, totalDelPedido } from './calculoDeVenta'
import { cantidadBaseDeLineas, componerLineas, excedeElStock, type PresentacionDeVenta } from './composicion'
import type { LineaDelPedido } from './formularioVenta'

/** Lo que carga el usuario por producto. */
export interface ItemDelPedido {
  productoId: string
  cajas: number
  unidades: number
}

/** Un producto con su precio en la versión aplicable y el stock de la ubicación, como los entrega el servidor. */
export interface ProductoConPrecio {
  productoId: string
  nombre: string
  precioReferencia: string | null
  unidadesReferencia: number | null
  stockBase: number | null
  /** Para resolver los alcances `CATEGORIA` y `MARCA` de los descuentos (ADR-050). */
  categoriaId?: string
  /** Vacío o ausente si el producto no tiene marca. */
  marcaId?: string
  /** Versión de lista de la que sale el precio (se congela por línea, PRC-23). */
  listaVersionId: string
  presentaciones: readonly PresentacionDeVenta[]
}

export interface LineaVisible {
  linea: LineaDelPedido
  productoNombre: string
  presentacionNombre: string
  cantidadBase: number
}

export interface PedidoArmado {
  lineas: LineaDelPedido[]
  visibles: LineaVisible[]
  total: Importe
  /** Mensaje por producto que no se puede vender como está pedido. */
  errores: Record<string, string>
  /** Productos cuyos datos de precio todavía no llegaron. */
  pendientes: string[]
  /** Productos cuyo pedido supera el stock conocido (aviso, no bloqueo). */
  superaStock: string[]
  /** Hay al menos una línea, ningún error y no falta ningún dato. */
  completo: boolean
}

export const MENSAJE_SIN_PRECIO = 'Producto sin precio en la lista: no se puede vender.'

function mensajeDe(error: unknown): string {
  return error instanceof Error ? error.message : 'La cantidad no es válida.'
}

export function armarPedido(
  items: readonly ItemDelPedido[],
  productos: ReadonlyMap<string, ProductoConPrecio | undefined>,
  idDeLinea: (productoId: string, presentacionId: string) => string,
): PedidoArmado {
  const lineas: LineaDelPedido[] = []
  const visibles: LineaVisible[] = []
  const errores: Record<string, string> = {}
  const pendientes: string[] = []
  const superaStock: string[] = []

  for (const item of items) {
    const producto = productos.get(item.productoId)
    if (producto === undefined) {
      pendientes.push(item.productoId)
      continue
    }
    if (producto.precioReferencia === null || producto.unidadesReferencia === null) {
      errores[item.productoId] = MENSAJE_SIN_PRECIO
      continue
    }
    try {
      const componidas = componerLineas(producto.presentaciones, item.cajas, item.unidades)
      for (const componida of componidas) {
        const bruto = calcularBrutoDelPedido(producto.precioReferencia, producto.unidadesReferencia, componida.cantidadBase)
        const linea: LineaDelPedido = {
          lineaId: idDeLinea(producto.productoId, componida.presentacionId),
          productoId: producto.productoId,
          presentacionId: componida.presentacionId,
          cantidad: componida.cantidad,
          listaVersionId: producto.listaVersionId,
          precioReferencia: producto.precioReferencia,
          unidadesReferencia: producto.unidadesReferencia,
          importeBruto: bruto.toFixed(2),
        }
        lineas.push(linea)
        visibles.push({
          linea,
          productoNombre: producto.nombre,
          presentacionNombre: componida.nombre,
          cantidadBase: componida.cantidadBase,
        })
      }
      if (excedeElStock(cantidadBaseDeLineas(componidas), producto.stockBase)) superaStock.push(producto.productoId)
    } catch (error) {
      errores[item.productoId] = mensajeDe(error)
    }
  }

  const total = totalDelPedido(visibles.map((v) => calcularBrutoDelPedido(v.linea.precioReferencia, v.linea.unidadesReferencia, v.cantidadBase)))
  const completo = lineas.length > 0 && pendientes.length === 0 && Object.keys(errores).length === 0
  return { lineas, visibles, total, errores, pendientes, superaStock, completo }
}

/** Un producto de `GET /ventas/precios`, tal como lo entrega la API. */
export interface ProductoParaVenderDeApi {
  producto_id: string
  nombre: string
  precio_referencia: string | null
  unidades_referencia: number | null
  stock_base: number | null
  categoria_id?: string
  marca_id?: string | null
  presentaciones: readonly {
    presentacion_id: string
    nombre: string
    unidades_base: number
    es_referencia: boolean
  }[]
}

/** Pasa la respuesta del servidor al producto del pedido; `listaVersionId` es la versión de la respuesta. */
export function aProductoConPrecio(producto: ProductoParaVenderDeApi, listaVersionId: string): ProductoConPrecio {
  return {
    productoId: producto.producto_id,
    nombre: producto.nombre,
    precioReferencia: producto.precio_referencia,
    unidadesReferencia: producto.unidades_referencia,
    stockBase: producto.stock_base,
    categoriaId: producto.categoria_id,
    marcaId: producto.marca_id ?? undefined,
    listaVersionId,
    presentaciones: producto.presentaciones.map((p) => ({
      presentacionId: p.presentacion_id,
      nombre: p.nombre,
      unidadesBase: p.unidades_base,
      esReferencia: p.es_referencia,
    })),
  }
}
