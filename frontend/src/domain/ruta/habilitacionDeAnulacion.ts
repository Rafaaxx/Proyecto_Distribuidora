import type { EstadoDeEnvio } from '../../lib/dispositivo/db'
import { LARGO_MAXIMO_DE_OBSERVACION } from './anulacionLocal'

/**
 * Cuándo se ofrece «Anular venta» en el teléfono y qué falta en el formulario (change 22d,
 * `design.md` D5, D9; VTA-20, VTA-22, VTA-24, CLI-03, SEG-06, RUT-09). Funciones puras: las
 * pantallas solo muestran el resultado.
 */
export type MotivoDeNoAnular =
  | 'SIN_PERMISO'
  | 'OTRA_JORNADA'
  | 'RECHAZADA'
  | 'YA_ANULADA'
  | 'JORNADA_NO_ABIERTA'
  | 'VERSION_BLOQUEADA'

export interface EntradaDeHabilitacion {
  /** Permisos del usuario en el bootstrap. */
  permisos: readonly string[]
  venta: { jornada_id: string; estado_envio: EstadoDeEnvio }
  /** Jornada de la sesión local. */
  jornadaDeLaSesionId: string
  /** Ya hay una fila en `anulaciones` para la venta. */
  tieneAnulacion: boolean
  /** El teléfono guardó que la jornada de la sesión ya no está abierta (D8). */
  jornadaNoAbierta: boolean
  /** La aplicación está por debajo de la versión mínima (`02` §6.6). */
  versionBloqueada: boolean
}

/** Por qué NO se ofrece «Anular venta»; `null` si se ofrece. */
export function motivoDeNoAnular(entrada: EntradaDeHabilitacion): MotivoDeNoAnular | null {
  if (!entrada.permisos.includes('ANULAR_VENTA')) return 'SIN_PERMISO'
  if (entrada.venta.jornada_id !== entrada.jornadaDeLaSesionId) return 'OTRA_JORNADA'
  if (entrada.venta.estado_envio === 'RECHAZADA') return 'RECHAZADA'
  if (entrada.tieneAnulacion) return 'YA_ANULADA'
  if (entrada.jornadaNoAbierta) return 'JORNADA_NO_ABIERTA'
  if (entrada.versionBloqueada) return 'VERSION_BLOQUEADA'
  return null
}

export type ErrorDeFormularioDeAnulacion = 'MOTIVO_REQUERIDO' | 'OBSERVACION_LARGA' | 'DEVOLUCION_REQUERIDA'

export interface EntradaDeFormularioDeAnulacion {
  motivoId: string
  observacion: string
  /** La venta tuvo cobro en el acto: solo entonces se pregunta la devolución. */
  tieneCobro: boolean
  esConsumidorFinal: boolean
  /** Elección del vendedor; `null` si todavía no eligió. */
  eleccion: boolean | null
}

/** Lo que falta para confirmar, en el orden del formulario (VTA-20, VTA-22, CLI-03). */
export function validarFormularioDeAnulacion(entrada: EntradaDeFormularioDeAnulacion): ErrorDeFormularioDeAnulacion[] {
  const errores: ErrorDeFormularioDeAnulacion[] = []
  if (entrada.motivoId === '') errores.push('MOTIVO_REQUERIDO')
  if (entrada.observacion.trim().length > LARGO_MAXIMO_DE_OBSERVACION) errores.push('OBSERVACION_LARGA')
  if (entrada.tieneCobro && !entrada.esConsumidorFinal && entrada.eleccion === null) errores.push('DEVOLUCION_REQUERIDA')
  return errores
}

export const TEXTO_DE_ERROR_DE_ANULACION: Readonly<Record<ErrorDeFormularioDeAnulacion, string>> = {
  MOTIVO_REQUERIDO: 'Elegí un motivo.',
  OBSERVACION_LARGA: `La observación admite hasta ${LARGO_MAXIMO_DE_OBSERVACION} caracteres.`,
  DEVOLUCION_REQUERIDA: 'Indicá si devolvés lo cobrado.',
}
