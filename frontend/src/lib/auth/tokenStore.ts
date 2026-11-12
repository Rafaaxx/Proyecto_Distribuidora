/**
 * Almacén del access token en memoria del proceso.
 *
 * ADR-017 y la spec `identidad/autenticacion-y-sesion` ("El access token es
 * de vida corta, viaja en memoria y no lleva permisos", "El refresh token
 * no es legible desde la aplicación") exigen que el access token NUNCA se
 * persista en el navegador: ni `localStorage`, ni `sessionStorage`, ni una
 * cookie legible desde JavaScript. Una variable de módulo cumple eso por
 * construcción: no hay ninguna llamada a una API de almacenamiento del
 * navegador en este archivo, y al recargar la página el motor de
 * JavaScript vuelve a evaluar el módulo desde cero, así que el valor
 * desaparece solo (tarea 13.2).
 *
 * El refresh token nunca pasa por acá: vive en la cookie `HttpOnly` que
 * fija el backend (`backend/app/api_v1/auth.py`); el frontend no puede
 * leerla ni necesita guardarla.
 */

let accessTokenEnMemoria: string | null = null

/**
 * ¿La sesión terminó y hay que ofrecer iniciar sesión? (tarea 11.2, **B1**)
 *
 * Antes de este flag, "no hay access token" significaba dos cosas distintas
 * y el código las tenía que adivinar:
 *
 * - **Página recién cargada o recién iniciada sesión**: el token no está
 *   porque vive solo en memoria (ADR-017), pero la cookie `HttpOnly` del
 *   refresh token sigue vigente. La primera petición da 401, dispara la
 *   renovación y el reintento trae los permisos. Si esto se tomara por
 *   sesión terminada, el usuario perdería el acceso en cada recarga.
 * - **Sesión terminada**: el backend rechazó la renovación. Volver a
 *   negociar solo vuelve a fallar.
 *
 * El único camino que limpia el access token es un `/auth/refresh`
 * rechazado (`httpClient.renovarAccessToken`), así que marcar acá es
 * exacto: `limpiarAccessToken()` significa "el servidor acaba de decir que
 * esta sesión no existe más".
 */
let sesionTerminadaEnProceso = false

/**
 * Aviso de cambios de token (`design.md` D2-A, tarea 5.1). `AdminScreen` se
 * suscribe una sola vez para invalidar o reiniciar la consulta `['yo']`
 * según el token nuevo. `tokenStore` no conoce React ni TanStack: solo
 * avisa con el valor nuevo (`string`) o con `null` si el token se limpió.
 */
type ListenerDeToken = (token: string | null) => void

const listenersDeToken = new Set<ListenerDeToken>()

/**
 * Suscribe `listener` a cada cambio de token. Devuelve una función para
 * desuscribirse. Si `listener` se desuscribe a sí mismo mientras se está
 * avisando, no interrumpe el aviso a los demás suscriptores (se itera
 * sobre una copia del conjunto).
 */
export function suscribirACambiosDeToken(listener: ListenerDeToken): () => void {
  listenersDeToken.add(listener)
  return () => {
    listenersDeToken.delete(listener)
  }
}

function avisarCambioDeToken(token: string | null): void {
  for (const listener of [...listenersDeToken]) {
    listener(token)
  }
}

export function obtenerAccessToken(): string | null {
  return accessTokenEnMemoria
}

/**
 * `true` cuando el backend rechazó la renovación y esta sesión ya no
 * existe. Lo consulta `obtenerYo()` para cortar en seco (tarea 11.2) y
 * `httpClient` para no volver a pedir `/auth/refresh`.
 */
export function sesionTerminada(): boolean {
  return sesionTerminadaEnProceso
}

export function fijarAccessToken(token: string): void {
  accessTokenEnMemoria = token
  sesionTerminadaEnProceso = false
  avisarCambioDeToken(token)
}

export function limpiarAccessToken(): void {
  accessTokenEnMemoria = null
  sesionTerminadaEnProceso = true
  avisarCambioDeToken(null)
}
