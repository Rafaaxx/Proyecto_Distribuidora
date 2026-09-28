import { apiFetch } from '../../lib/api/httpClient'
import { sesionTerminada } from '../../lib/auth/tokenStore'
import type { components } from '../../api/schema.gen'

/**
 * Acceso a `GET /api/v1/yo` (tarea 6.2, `design.md` D1-A). Tipado contra
 * `schema.gen.ts` -- nunca `any`. Es la única función que pide esta ruta:
 * `usePermisos()` la envuelve en `useQuery(['yo'])`.
 */
export type Yo = components['schemas']['YoResponse']

interface ProblemDetails {
  title?: string
  codigo?: string
}

const MENSAJE_GENERICO = 'No se pudieron obtener tus permisos.'

/**
 * Código del 401 que arma el cliente mismo cuando la sesión ya terminó
 * (tarea 11.2). No es un código de negocio: nunca sale de acá hacia el
 * servidor, y el servidor nunca lo devuelve. Sirve para que este 401 sea
 * indistinguible, para quien lo mira, del 401 de
 * `IDENTIDAD_ACCESS_TOKEN_INVALIDO` que devuelve el backend con un usuario
 * inactivo o un token inválido (ADR-028 D9.2-A), que es el otro caso en el
 * que la sesión no existe más. `AdminLayout` decide por `status`, no por
 * código (tarea 7.4), así que los dos ofrecen "Iniciar sesión".
 */
const CODIGO_SESION_TERMINADA = 'IDENTIDAD_SESION_TERMINADA'

/**
 * Error de `/yo` (tarea 6.2): conserva el `status` HTTP de la respuesta,
 * no solo el `codigo` de negocio, porque `design.md` D3-A distingue "la
 * consulta falló" de "la sesión terminó" (401 tras una renovación
 * fallida) para decidir si el menú ofrece reintentar o ir a iniciar
 * sesión (tarea 7.2).
 */
export class ErrorDeIdentidad extends Error {
  readonly status: number
  readonly codigo: string

  constructor(status: number, codigo: string, mensaje: string) {
    super(mensaje)
    this.name = 'ErrorDeIdentidad'
    this.status = status
    this.codigo = codigo
  }
}

async function errorDeIdentidadDesdeRespuesta(respuesta: Response): Promise<ErrorDeIdentidad> {
  let problema: ProblemDetails = {}
  try {
    problema = (await respuesta.json()) as ProblemDetails
  } catch {
    // Cuerpo no-JSON o vacío: se usa el mensaje de reserva.
  }
  return new ErrorDeIdentidad(respuesta.status, problema.codigo ?? 'ERROR_DESCONOCIDO', problema.title ?? MENSAJE_GENERICO)
}

export async function obtenerYo(): Promise<Yo> {
  // Fallo rápido con la sesión ya terminada (tarea 11.2, B1). Importa
  // sobre todo porque `AdminScreen` reinicia `['yo']` cuando se limpia el
  // token: si esta función fuera a la red, cada reinicio dispararía otra
  // renovación rechazada, que limpiaría el token otra vez, y así
  // indefinidamente, en vez de mostrar "Iniciar sesión".
  //
  // Solo aplica con la sesión *conocidamente* terminada, nunca por estar
  // sin token: al recargar la página no hay token y la sesión sigue viva
  // (se recupera con la cookie `HttpOnly` del refresh, ADR-017).
  if (sesionTerminada()) {
    throw new ErrorDeIdentidad(401, CODIGO_SESION_TERMINADA, MENSAJE_GENERICO)
  }

  const respuesta = await apiFetch('/yo')
  if (!respuesta.ok) {
    throw await errorDeIdentidadDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as Yo
}
