/**
 * PRC-22: importe bruto de una línea de venta (`design.md` D10 del change 13, `01` §7.3).
 *
 *     bruto = redondearImporte(precio de referencia x cantidad base / unidades de referencia)
 *
 * Función pura, espejo de `backend/app/modules/precios/domain/bruto_de_linea.py`: mismos
 * casos de `shared/fixtures/calculo/prc-22-bruto-de-linea.json` (`"motor": "prc22"`,
 * ADR-016). Un solo redondeo, al final, desde `lib/money.ts` (TR-03, ADR-010). El precio
 * unitario por presentación que se muestra se calcula con la misma función (cantidad base
 * igual a las unidades de la presentación) y NUNCA se usa para armar totales: `$1.433,33
 * x 3` daría `$4.299,99`, mientras que el bruto de 3 unidades es `$4.300,00`.
 *
 * Nada se convierte a `number` para calcular (INV-03): el precio entra como cadena exacta
 * y el producto y el cociente los hace decimal.js con la precisión ampliada de `lib/money`.
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

/** Error de dominio del bruto de línea: código estable igual al del backend. */
export class ErrorDeBrutoDeLinea extends Error {
  readonly codigo: string

  constructor(codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeBrutoDeLinea'
    this.codigo = codigo
  }
}

function esEnteroPositivo(valor: unknown): valor is number {
  return typeof valor === 'number' && Number.isInteger(valor) && valor >= 1
}

/**
 * `precioReferencia x cantidadBase / unidadesReferencia`, redondeado a dos decimales una
 * sola vez. `unidadesReferencia` y `cantidadBase` son enteros (INV-04): una cantidad base
 * no positiva o unas unidades de referencia menores que uno se rechazan con un
 * `ErrorDeBrutoDeLinea`; un precio `number` o una cadena que no es un decimal, con
 * `EntradaNoEsDineroExactoError` (INV-03).
 */
export function calcularBrutoDeLinea(
  precioReferencia: string,
  unidadesReferencia: number,
  cantidadBase: number,
): Importe {
  const precio = parsearImporteDesdeApi(precioReferencia)
  if (!esEnteroPositivo(unidadesReferencia)) {
    throw new ErrorDeBrutoDeLinea(
      'UNIDADES_REFERENCIA_INVALIDAS',
      `Las unidades de referencia deben ser un entero >= 1 (recibido ${String(unidadesReferencia)}).`,
    )
  }
  if (!esEnteroPositivo(cantidadBase)) {
    throw new ErrorDeBrutoDeLinea(
      'CANTIDAD_BASE_INVALIDA',
      `La cantidad base debe ser un entero positivo (recibido ${String(cantidadBase)}).`,
    )
  }
  return redondearImporte(precio.times(cantidadBase).div(unidadesReferencia))
}
