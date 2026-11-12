/**
 * Composición de las líneas de una venta en "cajas + unidades" (change 18a, tarea 12.1;
 * `design.md` D8; VTA-02, CAT-07, CAT-08, INV-04). Lógica pura, sin React: la pantalla pinta lo
 * que esto devuelve.
 *
 * Una línea es un producto en UNA presentación. "Cajas" es la presentación de referencia
 * (`es_referencia`, más de una unidad base) y "unidades sueltas" la presentación de 1 unidad
 * base, que puede no existir (CAT-07): sin ella no se ofrecen unidades. Si la referencia es la
 * de 1 unidad hay una sola presentación y no hay "cajas". El servidor valida igual (TR-10).
 */

import { CantidadInvalidaError } from '../stock/cantidades'

/** Presentación de venta de un producto (`usar_en_venta` y activa, como la entrega la API). */
export interface PresentacionDeVenta {
  presentacionId: string
  nombre: string
  unidadesBase: number
  esReferencia: boolean
}

/** Una línea armada por la composición: cantidad en la presentación y su equivalente en base. */
export interface LineaComponida {
  presentacionId: string
  nombre: string
  cantidad: number
  cantidadBase: number
}

/** Rango de `integer` de PostgreSQL (INV-04). */
const ENTERO_MAXIMO = 2_147_483_647

function presentacionDeUnidad(presentaciones: readonly PresentacionDeVenta[]): PresentacionDeVenta | undefined {
  return presentaciones.find((p) => p.unidadesBase === 1)
}

function presentacionDeCaja(presentaciones: readonly PresentacionDeVenta[]): PresentacionDeVenta | undefined {
  const referencia = presentaciones.find((p) => p.esReferencia)
  return referencia !== undefined && referencia.unidadesBase > 1 ? referencia : undefined
}

/** Si el producto se vende por caja: tiene referencia de más de una unidad. */
export function admiteCajas(presentaciones: readonly PresentacionDeVenta[]): boolean {
  return presentacionDeCaja(presentaciones) !== undefined
}

/** CAT-07: unidades sueltas solo si existe una presentación de 1 unidad base. */
export function admiteUnidadesSueltas(presentaciones: readonly PresentacionDeVenta[]): boolean {
  return presentacionDeUnidad(presentaciones) !== undefined
}

function esEnteroNoNegativo(valor: number): boolean {
  return Number.isSafeInteger(valor) && valor >= 0
}

/**
 * Arma las líneas de `cajas` + `unidades` (una parte en cero no genera línea). Lanza
 * `CantidadInvalidaError` ante una cantidad que no es entera no negativa, que no entra en 32 bits,
 * o que pide cajas o unidades sueltas que el producto no admite.
 */
export function componerLineas(
  presentaciones: readonly PresentacionDeVenta[],
  cajas: number,
  unidades: number,
): LineaComponida[] {
  if (!esEnteroNoNegativo(cajas) || !esEnteroNoNegativo(unidades)) {
    throw new CantidadInvalidaError('Las cajas y las unidades tienen que ser enteros mayores o iguales a cero.')
  }
  const caja = presentacionDeCaja(presentaciones)
  const unidad = presentacionDeUnidad(presentaciones)
  if (cajas > 0 && caja === undefined && !(unidad?.esReferencia ?? false)) {
    throw new CantidadInvalidaError('El producto no se vende por cajas.')
  }
  if (unidades > 0 && unidad === undefined) {
    throw new CantidadInvalidaError('El producto no admite unidades sueltas.')
  }

  const lineas: LineaComponida[] = []
  if (caja !== undefined) {
    if (cajas > 0) lineas.push(armar(caja, cajas))
    if (unidades > 0 && unidad !== undefined) lineas.push(armar(unidad, unidades))
  } else if (unidad !== undefined) {
    // Una sola presentación de 1 unidad: lo que se pida de "cajas" son unidades de esa misma línea.
    const total = cajas + unidades
    if (total > 0) lineas.push(armar(unidad, total))
  }
  if (cantidadBaseDeLineas(lineas) > ENTERO_MAXIMO) {
    throw new CantidadInvalidaError('La cantidad no entra en un entero de 32 bits.')
  }
  return lineas
}

function armar(presentacion: PresentacionDeVenta, cantidad: number): LineaComponida {
  return {
    presentacionId: presentacion.presentacionId,
    nombre: presentacion.nombre,
    cantidad,
    cantidadBase: cantidad * presentacion.unidadesBase,
  }
}

/** Suma de las cantidades base de las líneas. */
export function cantidadBaseDeLineas(lineas: readonly LineaComponida[]): number {
  return lineas.reduce((acumulado, linea) => acumulado + linea.cantidadBase, 0)
}

/** STK-05: lo pedido supera el stock conocido de la ubicación; sin stock conocido no avisa. */
export function excedeElStock(cantidadBase: number, stockBase: number | null): boolean {
  return stockBase !== null && cantidadBase > stockBase
}

/** Cantidad con la que entra un producto al pedido: una caja si se vende por caja; si no, una unidad. */
export function cantidadInicialDeProducto(presentaciones: readonly PresentacionDeVenta[]): { cajas: number; unidades: number } {
  return admiteCajas(presentaciones) ? { cajas: 1, unidades: 0 } : { cajas: 0, unidades: 1 }
}
