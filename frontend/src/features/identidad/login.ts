import type { DatosLogin } from '../../domain/identidad/loginSchema'
import { apiFetch } from '../../lib/api/httpClient'
import { fijarAccessToken } from '../../lib/auth/tokenStore'
import { obtenerOGenerarDispositivoId } from '../../lib/dispositivo/dispositivoId'

/**
 * Inicio de sesión compartido por `/admin` (envuelto en `useLogin`, TanStack Query) y `/ruta`
 * (se llama directo: ese área no usa TanStack, `CLAUDE.md` §2). Change 21, `design.md` D12.
 * El nombre del dispositivo es un dato descriptivo, no una regla de negocio.
 */
export interface RespuestaLogin {
  access_token: string
}

interface ProblemDetails {
  title?: string
}

/** Mensaje de reserva si la respuesta de error no trae `title` (respuesta malformada). */
const MENSAJE_GENERICO_DE_RESERVA = 'No se pudo iniciar sesión.'
const MENSAJE_SIN_CONEXION = 'No se pudo conectar con el servidor. Revisá tu conexión e intentá de nuevo.'

export class ErrorDeLogin extends Error {}

export async function iniciarSesionConContrasena(
  datos: DatosLogin,
  nombreDispositivo: string,
): Promise<RespuestaLogin> {
  const dispositivoId = await obtenerOGenerarDispositivoId()

  let respuesta: Response
  try {
    respuesta = await apiFetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        organizacion_slug: datos.organizacionSlug,
        usuario: datos.usuario,
        contrasena: datos.contrasena,
        dispositivo_id: dispositivoId,
        nombre_dispositivo: nombreDispositivo,
      }),
    })
  } catch {
    throw new ErrorDeLogin(MENSAJE_SIN_CONEXION)
  }

  if (!respuesta.ok) {
    const problema = (await respuesta.json()) as ProblemDetails
    // El mensaje viene tal cual del backend: la indistinguibilidad entre "contraseña incorrecta"
    // y "usuario inexistente" es una garantía del servidor; acá no se agrega ninguna distinción.
    throw new ErrorDeLogin(problema.title ?? MENSAJE_GENERICO_DE_RESERVA)
  }

  const datosToken = (await respuesta.json()) as RespuestaLogin
  fijarAccessToken(datosToken.access_token)
  return datosToken
}
