import { fijarAccessToken, limpiarAccessToken, obtenerAccessToken } from '../auth/tokenStore'
import { obtenerOGenerarDispositivoId } from '../dispositivo/dispositivoId'

/**
 * Cliente HTTP del área `/admin` sobre la API (`docs/02-arquitectura.md`
 * §12.1, ADR-017, tarea 13.3).
 *
 * Adjunta el access token en memoria (`Authorization: Bearer`) y envía
 * siempre `credentials: 'include'` para que el navegador mande la cookie
 * `HttpOnly` del refresh token, que este módulo nunca lee ni necesita leer.
 *
 * Ante un 401 (access token vencido o ausente), intenta una única
 * renovación con `/auth/refresh` y reintenta la petición original una sola
 * vez con el token nuevo. Si varias peticiones fallan a la vez, comparten
 * la misma renovación en vuelo (`renovacionEnCurso`): la segunda y
 * siguientes esperan la misma promesa en vez de disparar su propio
 * `/auth/refresh`.
 */

const BASE_URL = '/api/v1'

interface RespuestaTokenRenovado {
  access_token: string
}

let renovacionEnCurso: Promise<string | null> | null = null

async function renovarAccessToken(): Promise<string | null> {
  if (renovacionEnCurso) {
    return renovacionEnCurso
  }

  renovacionEnCurso = (async () => {
    const dispositivoId = await obtenerOGenerarDispositivoId()
    const respuesta = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dispositivo_id: dispositivoId }),
    })

    if (!respuesta.ok) {
      limpiarAccessToken()
      return null
    }

    const datos = (await respuesta.json()) as RespuestaTokenRenovado
    fijarAccessToken(datos.access_token)
    return datos.access_token
  })()

  try {
    return await renovacionEnCurso
  } finally {
    renovacionEnCurso = null
  }
}

function construirPeticion(path: string, init: RequestInit, token: string | null): [string, RequestInit] {
  const headers = new Headers(init.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return [`${BASE_URL}${path}`, { ...init, headers, credentials: 'include' }]
}

/**
 * Ejecuta una petición autenticada contra la API, renovando el access
 * token una sola vez si hace falta.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const [url, opciones] = construirPeticion(path, init, obtenerAccessToken())
  let respuesta = await fetch(url, opciones)

  if (respuesta.status === 401) {
    const tokenNuevo = await renovarAccessToken()
    if (tokenNuevo) {
      const [urlReintento, opcionesReintento] = construirPeticion(path, init, tokenNuevo)
      respuesta = await fetch(urlReintento, opcionesReintento)
    }
  }

  return respuesta
}
