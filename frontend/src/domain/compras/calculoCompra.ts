/**
 * CMP-02: cantidad base, costo base e importe neto de las líneas de una compra, total
 * neto y total de factura sugerido (`design.md` D1, D5, D15 del change 11,
 * **[ALTA: cálculo de costos y deuda]**).
 *
 * Funciones puras, espejo de `backend/app/modules/proveedores/domain/compras.py` (mismo
 * cálculo, mismos casos de `shared/fixtures/calculo/cmp-02-compra.json`). El costo base
 * reutiliza `calcularCostoBase` (CST-02): no se duplica la fórmula.
 *
 *     cantidadBase = cantidad x unidades de la presentación   (entero, INV-04)
 *     costoBase    = calcularCostoBase(...)                   (6 decimales, al final)
 *     importeNeto  = redondearImporte(cantidadBase x costoBase)
 *
 * El total neto es la suma de los importes de línea (TR-03). El total de factura
 * sugerido suma, por línea, `redondearImporte(importeNeto x (1 + alícuota))` (D1).
 * Nada se convierte a `number` para calcular (INV-03).
 */

import type { Importe } from '../../lib/money'
import {
  EntradaNoEsDineroExactoError,
  parsearImporteDesdeApi,
  redondearImporte,
} from '../../lib/money'
import { calcularCostoBase, ValorInvalidoError } from '../proveedores/costoBase'

export const MAXIMO_DE_LINEAS = 200

const DECIMALES_DE_CANTIDAD = 3
const DECIMALES_DE_IMPORTE = 2
const DECIMALES_DE_BONIFICACION = 6
const CANTIDAD_MAXIMA = '99999999999.999' // numeric(14,3)
const IMPORTE_MAXIMO = '999999999999.99' // numeric(14,2)
const COSTO_MAXIMO = '999999999999.999999' // numeric(18,6)
const CANTIDAD_BASE_MAXIMA = 2_147_483_647 // integer de PostgreSQL (INV-04)

/** Error de dominio de compras: código estable igual al del backend. */
export class ErrorDeCompra extends Error {
  readonly codigo: string
  readonly linea: number | undefined

  constructor(codigo: string, mensaje: string, linea?: number) {
    super(mensaje)
    this.name = 'ErrorDeCompra'
    this.codigo = codigo
    this.linea = linea
  }
}

/** Lo que el usuario informa de una línea y lo que el catálogo aporta (unidades de la
 * presentación y alícuota del producto). Los decimales viajan como cadena exacta. */
export interface EntradaDeLinea {
  unidadesPresentacion: number
  cantidad: string
  valor: string
  incluyeIva: boolean
  alicuota: string
  bonificacion: string
}

export interface LineaCalculada {
  cantidadBase: number
  costoBase: Importe
  importeNeto: Importe
  importeConIva: Importe
}

export interface TotalesDeCompra {
  lineas: LineaCalculada[]
  totalNeto: Importe
  totalFacturaSugerido: Importe
}

function aImporte(valor: string, codigo: string, mensaje: string): Importe {
  try {
    return parsearImporteDesdeApi(valor)
  } catch (error) {
    if (error instanceof EntradaNoEsDineroExactoError) {
      throw new ErrorDeCompra(codigo, mensaje)
    }
    throw error
  }
}

function calcularCantidadBase(cantidadTexto: string, unidades: number): number {
  const cantidad = aImporte(cantidadTexto, 'CANTIDAD_INVALIDA', 'La cantidad no es un decimal.')
  if (cantidad.lte(0)) {
    throw new ErrorDeCompra('CANTIDAD_INVALIDA', 'La cantidad tiene que ser mayor que cero.')
  }
  if (cantidad.decimalPlaces() > DECIMALES_DE_CANTIDAD || cantidad.gt(CANTIDAD_MAXIMA)) {
    throw new ErrorDeCompra(
      'CANTIDAD_INVALIDA',
      `La cantidad admite hasta ${String(DECIMALES_DE_CANTIDAD)} decimales y no más de ${CANTIDAD_MAXIMA}.`,
    )
  }
  const base = cantidad.mul(unidades)
  if (!base.isInteger()) {
    throw new ErrorDeCompra(
      'CANTIDAD_INVALIDA',
      `${cantidadTexto} x ${String(unidades)} unidades no da una cantidad entera en unidad base.`,
    )
  }
  if (base.gt(CANTIDAD_BASE_MAXIMA)) {
    throw new ErrorDeCompra('CANTIDAD_INVALIDA', 'La cantidad no entra en un entero de 32 bits.')
  }
  return base.toNumber()
}

function validarValor(valorTexto: string): void {
  const valor = aImporte(valorTexto, 'VALOR_INVALIDO', 'El valor no es un decimal.')
  if (valor.lte(0)) {
    throw new ErrorDeCompra('VALOR_INVALIDO', 'El valor por presentación debe ser mayor a cero.')
  }
  if (valor.decimalPlaces() > DECIMALES_DE_IMPORTE || valor.gt(IMPORTE_MAXIMO)) {
    throw new ErrorDeCompra(
      'VALOR_INVALIDO',
      `El valor admite hasta ${String(DECIMALES_DE_IMPORTE)} decimales y no más de ${IMPORTE_MAXIMO}.`,
    )
  }
}

function validarBonificacion(bonificacionTexto: string): void {
  const bonificacion = aImporte(
    bonificacionTexto,
    'BONIFICACION_INVALIDA',
    'La bonificación no es un decimal.',
  )
  if (
    bonificacion.lt(0) ||
    bonificacion.gte(1) ||
    bonificacion.decimalPlaces() > DECIMALES_DE_BONIFICACION
  ) {
    throw new ErrorDeCompra(
      'BONIFICACION_INVALIDA',
      'La bonificación debe estar entre 0 (inclusive) y 1 (exclusive), con hasta 6 decimales.',
    )
  }
}

/**
 * Cantidad base, costo base e importe neto de una línea (CMP-02, D5). Lanza
 * `ErrorDeCompra` con `CANTIDAD_INVALIDA`, `VALOR_INVALIDO`, `BONIFICACION_INVALIDA` o
 * `IMPORTE_INVALIDO`, los mismos códigos que el backend.
 */
export function calcularLinea(entrada: EntradaDeLinea): LineaCalculada {
  const cantidadBase = calcularCantidadBase(entrada.cantidad, entrada.unidadesPresentacion)
  validarValor(entrada.valor)
  validarBonificacion(entrada.bonificacion)

  let costoBase: Importe
  try {
    costoBase = calcularCostoBase(
      entrada.valor,
      entrada.incluyeIva,
      entrada.alicuota,
      entrada.bonificacion,
      entrada.unidadesPresentacion,
    )
  } catch (error) {
    if (error instanceof ValorInvalidoError) {
      throw new ErrorDeCompra('VALOR_INVALIDO', error.message)
    }
    throw error
  }
  if (costoBase.lte(0) || costoBase.gt(COSTO_MAXIMO)) {
    throw new ErrorDeCompra('VALOR_INVALIDO', 'El costo base resultante no es un costo válido.')
  }

  const importeNeto = redondearImporte(costoBase.mul(cantidadBase))
  if (importeNeto.gt(IMPORTE_MAXIMO)) {
    throw new ErrorDeCompra('IMPORTE_INVALIDO', `El importe de la línea supera ${IMPORTE_MAXIMO}.`)
  }
  const alicuota = parsearImporteDesdeApi(entrada.alicuota)
  const importeConIva = redondearImporte(importeNeto.mul(alicuota.add(1)))
  return { cantidadBase, costoBase, importeNeto, importeConIva }
}

/**
 * Totales de una compra (CMP-02, INV-07, D1, D5): de 1 a 200 líneas; el error de una
 * línea lleva su índice (0-based) en `linea`. `COMPRA_SIN_LINEAS` si la lista es vacía;
 * `LINEAS_INVALIDAS` si pasa de 200.
 */
export function calcularCompra(lineas: EntradaDeLinea[]): TotalesDeCompra {
  if (lineas.length < 1) {
    throw new ErrorDeCompra('COMPRA_SIN_LINEAS', 'Una compra necesita al menos una línea.')
  }
  if (lineas.length > MAXIMO_DE_LINEAS) {
    throw new ErrorDeCompra(
      'LINEAS_INVALIDAS',
      `Una compra admite hasta ${String(MAXIMO_DE_LINEAS)} líneas, no ${String(lineas.length)}.`,
    )
  }

  const calculadas = lineas.map((entrada, indice) => {
    try {
      return calcularLinea(entrada)
    } catch (error) {
      if (error instanceof ErrorDeCompra) {
        throw new ErrorDeCompra(error.codigo, error.message, indice)
      }
      throw error
    }
  })

  let totalNeto = parsearImporteDesdeApi('0')
  let sugerido = parsearImporteDesdeApi('0')
  for (const linea of calculadas) {
    totalNeto = totalNeto.add(linea.importeNeto)
    sugerido = sugerido.add(linea.importeConIva)
  }
  if (totalNeto.gt(IMPORTE_MAXIMO) || sugerido.gt(IMPORTE_MAXIMO)) {
    throw new ErrorDeCompra('IMPORTE_INVALIDO', `El total de la compra supera ${IMPORTE_MAXIMO}.`)
  }
  return {
    lineas: calculadas,
    totalNeto: redondearImporte(totalNeto),
    totalFacturaSugerido: redondearImporte(sugerido),
  }
}
