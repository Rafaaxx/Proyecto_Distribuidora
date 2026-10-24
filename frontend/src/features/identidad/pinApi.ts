import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'

/**
 * Acceso al PIN de autorización (change 18b, D21): `GET /identidad/usuarios` y
 * `POST /identidad/usuarios/{id}/pin` (`ADMIN_USUARIOS`), y "Mi PIN": `GET` y
 * `POST /yo/pin-autorizacion`. Tipado contra `schema.gen.ts`, nunca `any`. El PIN y la contraseña
 * existen solo mientras dura la llamada: no se guardan, no se registran y no se devuelven.
 */

export type UsuarioDeAdministracion = components['schemas']['UsuarioResponse']
export type EstadoDeMiPin = components['schemas']['MiPinEstadoResponse']

/** Error de dominio de la API del PIN: `codigo` estable (`IDENTIDAD_CONTRASENA_INCORRECTA`, ...). */
export class ErrorDePin extends Error {
  readonly codigo: string
  readonly estado: number

  constructor(codigo: string, mensaje: string, estado: number) {
    super(mensaje)
    this.name = 'ErrorDePin'
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
    const codigo = problema.codigo ?? (respuesta.status === 403 ? 'PERMISO_REQUERIDO' : 'ERROR_DESCONOCIDO')
    throw new ErrorDePin(codigo, problema.title ?? 'No se pudo completar la operación.', respuesta.status)
  }
  return (await respuesta.json()) as T
}

async function leerSinCuerpoOLanzar(respuesta: Response): Promise<void> {
  if (!respuesta.ok) await leerOLanzar<never>(respuesta)
}

function escritura(operationId: string, cuerpo: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(cuerpo),
  }
}

export async function listarUsuarios(): Promise<UsuarioDeAdministracion[]> {
  return leerOLanzar(await apiFetch('/identidad/usuarios'))
}

/** `PIN_AUTORIZACION_ROTAR` (204): define o cambia el PIN de otro usuario. */
export async function rotarPinDeUsuario(usuarioId: string, pin: string, operationId: string): Promise<void> {
  return leerSinCuerpoOLanzar(await apiFetch(`/identidad/usuarios/${usuarioId}/pin`, escritura(operationId, { pin })))
}

export async function obtenerEstadoDeMiPin(): Promise<EstadoDeMiPin> {
  return leerOLanzar(await apiFetch('/yo/pin-autorizacion'))
}

/** `PIN_AUTORIZACION_PROPIO_DEFINIR` (204): el usuario sale del token, nunca del cuerpo. */
export async function definirMiPin(pin: string, passwordActual: string, operationId: string): Promise<void> {
  return leerSinCuerpoOLanzar(
    await apiFetch('/yo/pin-autorizacion', escritura(operationId, { pin, password_actual: passwordActual })),
  )
}
