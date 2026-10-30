import { mensajeDeErrorDeUsuarios, type ContextoDeError } from '../../../domain/identidad/usuarios'
import { ErrorDeApiRoles } from '../../../features/identidad/rolesApi'
import { ErrorDeApiUsuarios } from '../../../features/identidad/usuariosApi'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION } from '../precios/errores'

const MENSAJE_GENERICO = 'No se pudo completar la operación.'

/**
 * Texto para mostrar de un error de las pantallas de usuarios y roles (change 20b, D16): sin
 * conexión avisa que hace falta (estos comandos son solo con conexión); un error de dominio se
 * explica en palabras simples por su código; cualquier otra cosa, un mensaje general.
 */
export function describirErrorDeUsuarios(error: unknown, contexto: ContextoDeError = {}): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  if (error instanceof ErrorDeApiUsuarios || error instanceof ErrorDeApiRoles) {
    return mensajeDeErrorDeUsuarios(error.codigo, error.message, contexto)
  }
  return MENSAJE_GENERICO
}

export { AVISO_SIN_CONEXION }
export { estaSinConexion } from '../precios/errores'
