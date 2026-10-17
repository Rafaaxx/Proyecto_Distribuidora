import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'

/**
 * Acceso a la administración de permisos de rol (change 17b, D7, D9): `GET /identidad/roles`,
 * `GET /identidad/permisos` y `PUT /identidad/roles/{id}/permisos` (`ADMIN_USUARIOS`). Tipado
 * contra `schema.gen.ts`, nunca `any`. El `Operation-Id` lo conserva quien llama (INV-06).
 */

export type RolConPermisos = components['schemas']['RolConTopeYPermisosResponse']
export type PermisoDeCatalogo = components['schemas']['PermisoCatalogoResponse']

/** Error de dominio de la API de roles: `codigo` estable (`IDENTIDAD_SIN_ADMINISTRADOR`, ...). */
export class ErrorDeApiRoles extends Error {
  readonly codigo: string
  readonly estado: number

  constructor(codigo: string, mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorDeApiRoles'
    this.codigo = codigo
    this.estado = estado
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

async function leerOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    let problema: ProblemDetails = {}
    try {
      problema = (await respuesta.json()) as ProblemDetails
    } catch {
      // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
    }
    throw new ErrorDeApiRoles(
      respuesta.status === 403 ? 'PERMISO_REQUERIDO' : (problema.codigo ?? 'ERROR_DESCONOCIDO'),
      problema.title ?? 'No se pudo completar la operación.',
      respuesta.status,
    )
  }
  return (await respuesta.json()) as T
}

export async function listarRolesConPermisos(): Promise<RolConPermisos[]> {
  return leerOLanzar(await apiFetch('/identidad/roles'))
}

export async function listarCatalogoDePermisos(): Promise<PermisoDeCatalogo[]> {
  return leerOLanzar(await apiFetch('/identidad/permisos'))
}

export async function cambiarPermisosDeRol(
  rolId: string,
  permisos: string[],
  operationId: string,
): Promise<components['schemas']['RolResponse']> {
  return leerOLanzar(
    await apiFetch(`/identidad/roles/${rolId}/permisos`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
      body: JSON.stringify({ permisos }),
    }),
  )
}
