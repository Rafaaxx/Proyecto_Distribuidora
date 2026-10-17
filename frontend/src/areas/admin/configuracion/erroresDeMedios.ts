import { mensajeDeErrorDeMedioPago } from '../../../domain/configuracion/medioPago'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'

export { AVISO_SIN_CONEXION, estaSinConexion }

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

/**
 * Traduce el error de una mutación de medios de pago a lo que la pantalla muestra. Un error de RED
 * (agotados los reintentos) es el aviso general: los comandos de medios son `ONLINE` puros y no se
 * encola nada (`02` §6.5).
 */
export function describirErrorDeMedio(error: unknown): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  if (error instanceof ErrorDeConfiguracion) return mensajeDeErrorDeMedioPago(error.codigo, error.message)
  return MENSAJE_GENERICO
}
