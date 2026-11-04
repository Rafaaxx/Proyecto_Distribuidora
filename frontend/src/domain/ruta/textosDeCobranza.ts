import { parsearImporteDesdeApi } from '../../lib/money'
import { MEDIOS_MAXIMOS, OBSERVACION_MAXIMA, type ErrorDeCobranzaLocal, type EvaluacionDeCobranzaLocal } from './cobranzaLocal'
import { formatearDinero } from './lecturasLocales'

/**
 * Textos de pantalla de la cobranza del teléfono (change 23, `design.md` D4, D8; COB-01, COB-02,
 * INV-08, CC-04). Funciones puras: las pantallas solo los muestran. Los de confirmación y de saldo
 * a favor son los aprobados en 0.2; los de error de formulario siguen el estilo de los de la
 * anulación.
 */
export function textoDeConfirmacionDeCobranza(importe: string, cliente: string): string {
  return `¿Registrar la cobranza de ${formatearDinero(importe)} a ${cliente}?`
}

export function textoDeSaldoAFavor(importe: string): string {
  return `El cliente queda con ${formatearDinero(importe)} a favor.`
}

const TEXTOS_DE_ERROR: Readonly<Record<Exclude<ErrorDeCobranzaLocal, 'MEDIOS_NO_SUMAN'>, string>> = {
  SIN_CLIENTE: 'Elegí el cliente.',
  CONSUMIDOR_FINAL: 'Al consumidor final no se le registran cobranzas.',
  IMPORTE_INVALIDO: 'El importe tiene que ser mayor que cero y tener hasta dos decimales.',
  SIN_MEDIOS: 'Cargá al menos un medio de pago.',
  MEDIOS_DEMASIADOS: `Se pueden cargar hasta ${MEDIOS_MAXIMOS} medios de pago.`,
  MEDIO_INVALIDO: 'Cada medio necesita el medio de pago elegido y un importe mayor que cero.',
  REFERENCIA_FALTANTE: 'Falta la referencia de un medio que la pide.',
  OBSERVACION_LARGA: `La observación puede tener hasta ${OBSERVACION_MAXIMA} caracteres.`,
}

/** «Los medios no suman el importe: faltan $ 10,00.» o «…sobran $ 20,50.» (INV-08). */
function textoDeDiferencia(faltante: string): string {
  const diferencia = parsearImporteDesdeApi(faltante)
  const dicho = diferencia.isNegative() ? `sobran ${formatearDinero(diferencia.neg().toFixed(2))}` : `faltan ${formatearDinero(faltante)}`
  return `Los medios no suman el importe: ${dicho}.`
}

/** Los textos de los errores de la evaluación, en el orden en que se detectaron. */
export function textosDeErroresDeCobranza(evaluacion: Pick<EvaluacionDeCobranzaLocal, 'errores' | 'faltante'>): string[] {
  return evaluacion.errores.map((error) =>
    error === 'MEDIOS_NO_SUMAN' ? textoDeDiferencia(evaluacion.faltante) : TEXTOS_DE_ERROR[error],
  )
}
