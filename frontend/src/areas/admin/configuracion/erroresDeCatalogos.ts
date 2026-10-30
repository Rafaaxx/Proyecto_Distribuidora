import {
  mensajeDeErrorDeAlicuota,
  mensajeDeErrorDeMotivo,
  mensajeDeErrorDeRedondeo,
} from '../../../domain/configuracion/catalogos'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'

export { AVISO_SIN_CONEXION, estaSinConexion }

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

/**
 * Traduce el error de una mutación de motivos, alícuotas o redondeo por defecto a lo que la pantalla
 * muestra (change 20c, D12). Un error de RED (agotados los reintentos) es el aviso general: estos
 * comandos son `ONLINE` puros y no se encola nada (`02` §6.5).
 */
function describir(error: unknown, traducir: (error: ErrorDeConfiguracion) => string): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  if (error instanceof ErrorDeConfiguracion) return traducir(error)
  return MENSAJE_GENERICO
}

export const describirErrorDeMotivo = (error: unknown) =>
  describir(error, (e) => mensajeDeErrorDeMotivo(e.codigo, e.message))

export const describirErrorDeAlicuota = (error: unknown) =>
  describir(error, (e) => mensajeDeErrorDeAlicuota(e.codigo, e.message, e.productos))

export const describirErrorDeRedondeo = (error: unknown) =>
  describir(error, (e) => mensajeDeErrorDeRedondeo(e.codigo, e.message))
