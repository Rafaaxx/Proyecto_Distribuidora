import { calcularFaltanteDeMedios, esImporteValido, type MedioDePagoDeFormulario } from '../pagos-proveedores/formularioPago'
import { calcularSaldoResultante } from '../cobranzas/formularioCobranza'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'

/**
 * Reglas locales de la cobranza del teléfono (change 23, `design.md` D3, D4; COB-01, COB-02, INV-08,
 * INV-03, CLI-03, CC-04). Función pura: valida el formulario ANTES de encolar y calcula el saldo
 * actual, el resultante y si queda a favor. Reutiliza la validación de importes y la suma de medios
 * de la cobranza y del pago a proveedor (`domain/cobranzas/formularioCobranza.ts`,
 * `domain/pagos-proveedores/formularioPago.ts`): no las duplica. Los importes nunca pasan por
 * `number`. El servidor vuelve a validar (TR-10); esto evita producir `MEDIOS_NO_SUMAN_IMPORTE`
 * y `REFERENCIA_FALTANTE` desde el teléfono.
 */
export const OBSERVACION_MAXIMA = 500
export const MEDIOS_MAXIMOS = 20

export type ErrorDeCobranzaLocal =
  | 'SIN_CLIENTE'
  | 'CONSUMIDOR_FINAL'
  | 'IMPORTE_INVALIDO'
  | 'SIN_MEDIOS'
  | 'MEDIOS_DEMASIADOS'
  | 'MEDIO_INVALIDO'
  | 'REFERENCIA_FALTANTE'
  | 'MEDIOS_NO_SUMAN'
  | 'OBSERVACION_LARGA'

/** Los medios activos del bootstrap con los que se puede cobrar. */
export interface MedioDeCobranzaLocal {
  id: string
  nombre: string
  requiere_referencia: boolean
}

export interface EntradaDeCobranzaLocal {
  cliente: { id: string; nombre: string; es_consumidor_final: boolean } | null
  /** Saldo local actual del cliente (CRE-08), o `null` si todavía no se eligió cliente. */
  saldoActual: string | null
  importe: string
  observacion: string
  medios: MedioDePagoDeFormulario[]
  mediosPago: readonly MedioDeCobranzaLocal[]
}

export interface EvaluacionDeCobranzaLocal {
  valida: boolean
  errores: ErrorDeCobranzaLocal[]
  /** Importe normalizado a dos decimales; `null` si no es válido. */
  importe: string | null
  /** Observación recortada; `null` si queda vacía. */
  observacion: string | null
  /** Medios normalizados para el sobre; vacío mientras la cobranza no es válida. */
  medios: { medio_pago_id: string; importe: string; referencia: string | null }[]
  /** Lo que falta (positivo) o sobra (negativo) para que los medios sumen el importe (INV-08). */
  faltante: string
  saldoActual: string | null
  /** Saldo del cliente después de cobrar (CC-04: negativo es a favor); `null` sin cliente. */
  saldoResultante: string | null
  quedaAFavor: boolean
  importeAFavor: string | null
}

function medioConImporteValido(medio: MedioDePagoDeFormulario): boolean {
  return esImporteValido(medio.importe)
}

export function evaluarCobranzaLocal(entrada: EntradaDeCobranzaLocal): EvaluacionDeCobranzaLocal {
  const errores: ErrorDeCobranzaLocal[] = []
  const { cliente } = entrada

  if (cliente === null) errores.push('SIN_CLIENTE')
  else if (cliente.es_consumidor_final) errores.push('CONSUMIDOR_FINAL')

  const importeValido = esImporteValido(entrada.importe)
  if (!importeValido) errores.push('IMPORTE_INVALIDO')

  const observacion = entrada.observacion.trim() === '' ? null : entrada.observacion.trim()
  if (observacion !== null && observacion.length > OBSERVACION_MAXIMA) errores.push('OBSERVACION_LARGA')

  if (entrada.medios.length === 0) errores.push('SIN_MEDIOS')
  if (entrada.medios.length > MEDIOS_MAXIMOS) errores.push('MEDIOS_DEMASIADOS')
  const porId = new Map(entrada.mediosPago.map((medio) => [medio.id, medio]))
  if (entrada.medios.some((m) => !porId.has(m.medioPagoId) || !medioConImporteValido(m))) errores.push('MEDIO_INVALIDO')
  if (entrada.medios.some((m) => porId.get(m.medioPagoId)?.requiere_referencia === true && m.referencia.trim() === '')) {
    errores.push('REFERENCIA_FALTANTE')
  }

  const faltante = calcularFaltanteDeMedios(entrada.importe, entrada.medios)
  if (importeValido && entrada.medios.length > 0 && !faltante.isZero()) errores.push('MEDIOS_NO_SUMAN')

  const valida = errores.length === 0
  const saldoResultante =
    entrada.saldoActual === null ? null : calcularSaldoResultante(entrada.saldoActual, entrada.importe).toFixed(2)
  const quedaAFavor = saldoResultante !== null && parsearImporteDesdeApi(saldoResultante).isNegative()

  return {
    valida,
    errores,
    importe: importeValido ? redondearImporte(entrada.importe.trim()).toFixed(2) : null,
    observacion,
    medios: valida
      ? entrada.medios.map((medio) => ({
          medio_pago_id: medio.medioPagoId,
          importe: redondearImporte(medio.importe.trim()).toFixed(2),
          referencia: medio.referencia.trim() === '' ? null : medio.referencia.trim(),
        }))
      : [],
    faltante: faltante.toFixed(2),
    saldoActual: entrada.saldoActual,
    saldoResultante,
    quedaAFavor,
    importeAFavor: quedaAFavor && saldoResultante !== null ? parsearImporteDesdeApi(saldoResultante).neg().toFixed(2) : null,
  }
}
