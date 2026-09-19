/**
 * Redondeo de dinero (`docs/02-arquitectura.md` §10.3, INV-03).
 *
 * Único módulo del frontend que cuantiza importes, costos y porcentajes.
 * Usa decimal.js configurado con `ROUND_HALF_UP`, con el mismo contrato de
 * `backend/app/core/money.py`: `redondearImporte` (2 decimales) y
 * `redondearCosto` (6 decimales). Ningún importe se convierte a `number`
 * nativo para calcular -- solo `formatearImporte` lo hace, y solo para
 * mostrar.
 */

import Decimal from 'decimal.js'

/** Instancia de decimal.js dedicada a dinero: `ROUND_HALF_UP` explícito. */
const DecimalDinero = Decimal.clone({ rounding: Decimal.ROUND_HALF_UP })

export type Importe = InstanceType<typeof DecimalDinero>

/** La entrada no es un valor decimal exacto (INV-03). */
export class EntradaNoEsDineroExactoError extends Error {
  constructor(mensaje: string) {
    super(mensaje)
    this.name = 'EntradaNoEsDineroExactoError'
  }
}

function aDecimalExacto(valor: string | Importe): Importe {
  // `typeof valor === 'number'` cubre el flotante binario nativo de
  // JavaScript, incluido el caso en que llega desde código sin tipar; en
  // TypeScript estricto la firma ya lo excluye, pero la guardia en runtime
  // es la que realmente cierra INV-03.
  if (typeof valor === 'number') {
    throw new EntradaNoEsDineroExactoError(
      `No se puede redondear un number nativo: ${String(valor)} ` +
        '(INV-03: usar una cadena numérica exacta o un Importe ya construido)',
    )
  }

  if (valor instanceof DecimalDinero) {
    return valor
  }

  if (typeof valor === 'string') {
    if (!/^-?\d+(\.\d+)?$/.test(valor.trim())) {
      throw new EntradaNoEsDineroExactoError(
        `La cadena "${valor}" no representa un valor decimal exacto`,
      )
    }
    return new DecimalDinero(valor)
  }

  throw new EntradaNoEsDineroExactoError(
    `Tipo de entrada no soportado para redondeo de dinero: ${typeof valor}`,
  )
}

/**
 * Cuantiza un importe a 2 decimales con `ROUND_HALF_UP` (`NUMERIC(14,2)`).
 *
 * El medio se desempata siempre alejándose de cero: `0.125 -> 0.13`,
 * `-0.125 -> -0.13`.
 */
export function redondearImporte(valor: string | Importe): Importe {
  return aDecimalExacto(valor).toDecimalPlaces(2)
}

/**
 * Cuantiza un costo por unidad base o un porcentaje a 6 decimales con
 * `ROUND_HALF_UP` (`NUMERIC(18,6)` / `NUMERIC(9,6)`, `design.md` D4).
 */
export function redondearCosto(valor: string | Importe): Importe {
  return aDecimalExacto(valor).toDecimalPlaces(6)
}

/**
 * Convierte la cadena de un importe recibida de la API (`"31250.00"`) en un
 * valor decimal exacto, sin pasar en ningún punto por `number` (`02` §10.3).
 */
export function parsearImporteDesdeApi(valorApi: string): Importe {
  return aDecimalExacto(valorApi)
}

/**
 * Formatea un importe ya redondeado para mostrarlo en pantalla, con dos
 * decimales fijos. Es el único punto donde el valor se convierte a texto
 * para el usuario; nunca se usa el resultado para volver a calcular.
 */
export function formatearImporte(importe: Importe): string {
  return importe.toFixed(2)
}
