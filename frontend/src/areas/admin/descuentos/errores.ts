import { ErrorDeApiDescuentos } from '../../../features/descuentos/errores'
import { esErrorDeRed } from '../../../features/descuentos/hooks'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'

export { AVISO_SIN_CONEXION, estaSinConexion }

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

export interface ErrorDePantalla {
  /** Código estable del servidor, o `null` si no es un rechazo de dominio. */
  codigo: string | null
  mensaje: string
}

/**
 * Traduce el error de una mutación de descuentos a lo que la pantalla muestra. Un error de RED
 * (agotados los reintentos) es un aviso general: todas las escrituras de descuentos son `ONLINE`
 * puras y no se encola nada (`02` §6.5, ADR-012). El aviso y la comprobación de conexión son los
 * mismos que usan las pantallas de precios.
 */
export function describirError(error: unknown): ErrorDePantalla {
  if (esErrorDeRed(error)) return { codigo: null, mensaje: AVISO_SIN_CONEXION }
  if (error instanceof ErrorDeApiDescuentos) return { codigo: error.codigo, mensaje: error.message }
  return { codigo: null, mensaje: MENSAJE_GENERICO }
}
