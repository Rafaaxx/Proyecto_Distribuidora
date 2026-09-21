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

export function obtenerAccessToken(): string | null {
  return accessTokenEnMemoria
}

export function fijarAccessToken(token: string): void {
  accessTokenEnMemoria = token
}

export function limpiarAccessToken(): void {
  accessTokenEnMemoria = null
}
