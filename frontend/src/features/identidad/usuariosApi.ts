import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'

/**
 * Acceso a la administración de usuarios (change 20b, D1, D16, D20): `GET/POST /identidad/usuarios`,
 * `GET/PUT /identidad/usuarios/{id}`, `POST .../baja`, `POST .../reactivacion`, `PUT .../rol`,
 * `POST .../contrasena`, `PUT .../tope-descuento` (`ADMIN_USUARIOS`) y "Mi contraseña"
 * (`POST /yo/contrasena`, cualquier usuario autenticado). Tipado contra `schema.gen.ts`, nunca
 * `any`. El `Operation-Id` lo conserva quien llama (INV-06). Las contraseñas existen solo mientras
 * dura la llamada: no se guardan, no se registran y no se devuelven (ADR-056).
 */

export type UsuarioDetalle = components['schemas']['UsuarioDetalleResponse']
export type UsuarioCambiado = components['schemas']['UsuarioCambioResponse']
export type UsuarioCreado = components['schemas']['UsuarioResponse']
export type DatosDeAltaParaApi = components['schemas']['CrearUsuarioRequest']

export interface FiltrosDeUsuarios {
  estado?: 'ACTIVO' | 'INACTIVO'
  rolId?: string
  conTopePropio?: boolean
}

/** Error de dominio de la API de usuarios: `codigo` estable (`IDENTIDAD_AUTOBAJA`, ...). */
export class ErrorDeApiUsuarios extends Error {
  readonly codigo: string
  readonly estado: number

  constructor(codigo: string, mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorDeApiUsuarios'
    this.codigo = codigo
    this.estado = estado
  }
}

interface ProblemDetails {
  title?: string
  codigo?: string
}

async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeApiUsuarios> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  // El código del servidor manda (un 403 puede ser `IDENTIDAD_CONTRASENA_INCORRECTA`, no solo falta de permiso).
  const codigo = problema.codigo ?? (respuesta.status === 403 ? 'PERMISO_REQUERIDO' : 'ERROR_DESCONOCIDO')
  return new ErrorDeApiUsuarios(codigo, problema.title ?? 'No se pudo completar la operación.', respuesta.status)
}

async function leerOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta)
  return (await respuesta.json()) as T
}

async function leerSinCuerpoOLanzar(respuesta: Response): Promise<void> {
  if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta)
}

function escritura(metodo: 'POST' | 'PUT', operationId: string, cuerpo?: unknown): RequestInit {
  return {
    method: metodo,
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    ...(cuerpo === undefined ? {} : { body: JSON.stringify(cuerpo) }),
  }
}

export async function listarUsuariosDetalle(filtros: FiltrosDeUsuarios = {}): Promise<UsuarioDetalle[]> {
  const params = new URLSearchParams()
  if (filtros.estado) params.set('estado', filtros.estado)
  if (filtros.rolId) params.set('rol_id', filtros.rolId)
  if (filtros.conTopePropio) params.set('con_tope_propio', 'true')
  const consulta = params.toString()
  return leerOLanzar(await apiFetch(consulta === '' ? '/identidad/usuarios' : `/identidad/usuarios?${consulta}`))
}

export async function obtenerUsuario(usuarioId: string): Promise<UsuarioDetalle> {
  return leerOLanzar(await apiFetch(`/identidad/usuarios/${usuarioId}`))
}

/** `USUARIO_CREAR`: la contraseña viaja una vez, en el cuerpo del alta. */
export async function crearUsuario(datos: DatosDeAltaParaApi, operationId: string): Promise<UsuarioCreado> {
  return leerOLanzar(await apiFetch('/identidad/usuarios', escritura('POST', operationId, datos)))
}

export async function modificarUsuario(
  usuarioId: string,
  datos: { nombre: string; email: string | null },
  operationId: string,
): Promise<UsuarioCambiado> {
  return leerOLanzar(await apiFetch(`/identidad/usuarios/${usuarioId}`, escritura('PUT', operationId, datos)))
}

export async function darDeBajaUsuario(
  usuarioId: string,
  observacion: string | null,
  operationId: string,
): Promise<UsuarioCambiado> {
  return leerOLanzar(
    await apiFetch(`/identidad/usuarios/${usuarioId}/baja`, escritura('POST', operationId, { observacion })),
  )
}

export async function reactivarUsuario(usuarioId: string, operationId: string): Promise<UsuarioCambiado> {
  return leerOLanzar(await apiFetch(`/identidad/usuarios/${usuarioId}/reactivacion`, escritura('POST', operationId)))
}

export async function cambiarRolDeUsuario(
  usuarioId: string,
  rolId: string,
  operationId: string,
): Promise<UsuarioCambiado> {
  return leerOLanzar(
    await apiFetch(`/identidad/usuarios/${usuarioId}/rol`, escritura('PUT', operationId, { rol_id: rolId })),
  )
}

/** `USUARIO_CONTRASENA_RESTABLECER` (204): la contraseña nueva viaja una vez. */
export async function restablecerContrasenaDeUsuario(
  usuarioId: string,
  contrasena: string,
  operationId: string,
): Promise<void> {
  return leerSinCuerpoOLanzar(
    await apiFetch(`/identidad/usuarios/${usuarioId}/contrasena`, escritura('POST', operationId, { contrasena })),
  )
}

/** `USUARIO_TOPE_DESCUENTO_DEFINIR`: fracción string o `null` para volver al tope del rol. */
export async function definirTopeDeUsuario(
  usuarioId: string,
  topeDescuento: string | null,
  operationId: string,
): Promise<UsuarioCambiado> {
  return leerOLanzar(
    await apiFetch(
      `/identidad/usuarios/${usuarioId}/tope-descuento`,
      escritura('PUT', operationId, { tope_descuento: topeDescuento }),
    ),
  )
}

/** `CONTRASENA_PROPIA_CAMBIAR` (204): el usuario sale del token, nunca del cuerpo (D20). */
export async function cambiarMiContrasena(
  passwordActual: string,
  passwordNueva: string,
  operationId: string,
): Promise<void> {
  return leerSinCuerpoOLanzar(
    await apiFetch(
      '/yo/contrasena',
      escritura('POST', operationId, { password_actual: passwordActual, password_nueva: passwordNueva }),
    ),
  )
}

/** `USUARIO_DESBLOQUEAR` (204, ADR-057): borra los intentos fallidos de inicio de sesión. */
export async function desbloquearUsuario(usuarioId: string, operationId: string): Promise<void> {
  return leerSinCuerpoOLanzar(await apiFetch(`/identidad/usuarios/${usuarioId}/desbloqueo`, escritura('POST', operationId)))
}
