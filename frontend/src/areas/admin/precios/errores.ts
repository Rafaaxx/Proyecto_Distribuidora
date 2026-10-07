import { ErrorDePrecios } from '../../../features/precios/errores'
import { esErrorDeRed } from '../../../features/precios/hooks'

export const AVISO_SIN_CONEXION =
  'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

export interface ErrorDePantalla {
  /** Código estable del servidor, o `null` si no es un rechazo de dominio. */
  codigo: string | null
  mensaje: string
}

/**
 * Traduce el error de una mutación de precios a lo que la pantalla muestra. Un error de RED
 * (agotados los reintentos) es un aviso general: todas las escrituras de precios son `ONLINE`
 * puras y no se encola nada (`02` §6.5, ADR-012).
 */
export function describirError(error: unknown): ErrorDePantalla {
  if (esErrorDeRed(error)) return { codigo: null, mensaje: AVISO_SIN_CONEXION }
  if (error instanceof ErrorDePrecios) return { codigo: error.codigo, mensaje: error.message }
  return { codigo: null, mensaje: MENSAJE_GENERICO }
}

/**
 * El navegador sabe que no hay conexión: las escrituras de precios son `ONLINE` puras, así que
 * la pantalla avisa y NO envía el comando ni lo encola (`02` §6.5, ADR-012).
 */
export function estaSinConexion(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false
}
