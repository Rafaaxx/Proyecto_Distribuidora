/**
 * Condición frente al IVA de la organización (11b, CST-06, `design.md` D1, D10). Lógica pura:
 * la pantalla de configuración fiscal solo la llama y pinta el resultado.
 */
import type { CondicionIva, ResumenReglaIva } from '../../features/configuracion/api'

/** Dominio cerrado de `03` §4, en el orden en que se ofrece. */
export const CONDICIONES_IVA: readonly CondicionIva[] = ['RESPONSABLE_INSCRIPTO', 'MONOTRIBUTO', 'EXENTO']

const ETIQUETAS: Record<CondicionIva, string> = {
  RESPONSABLE_INSCRIPTO: 'Responsable inscripto',
  MONOTRIBUTO: 'Monotributo',
  EXENTO: 'Exento',
}

export function etiquetaDeCondicionIva(condicion: CondicionIva): string {
  return ETIQUETAS[condicion]
}

/** CST-06: solo un responsable inscripto computa crédito fiscal de IVA en compras. */
export function computaCreditoFiscalDe(condicion: CondicionIva): boolean {
  return condicion === 'RESPONSABLE_INSCRIPTO'
}

/**
 * Cuántos costos vigentes se calcularon con la regla que deja de regir al pasar a `destino`
 * (D10): son los que conviene volver a informar, porque el cambio no es retroactivo.
 */
export function costosParaRevisar(destino: CondicionIva, resumen: ResumenReglaIva): number {
  return computaCreditoFiscalDe(destino) ? resumen.sin_credito_fiscal : resumen.con_credito_fiscal
}
