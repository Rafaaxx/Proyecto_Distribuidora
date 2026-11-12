/**
 * Detección de violaciones de la política de seguridad de contenido (CSP) en los mensajes de la
 * consola de Chromium (change 28, D9, D14; `02` §18). Funciones puras: las usa el accesorio de
 * `fixtures.ts` y las prueba Vitest.
 */

/** Chromium informa una violación como un error de consola que nombra la directiva
 * («… Content Security Policy directive: "script-src 'self'"»). Empieza con «Refused to …» o,
 * en las versiones recientes, con «Loading the … violates the following …». */
export function esViolacionDeCsp(mensaje: string): boolean {
  return /^Refused to .*Content Security Policy/s.test(mensaje) || /violates the following Content Security Policy directive/.test(mensaje)
}

/** La directiva que el navegador dice haber violado, o `null` si el mensaje no la nombra. */
export function directivaViolada(mensaje: string): string | null {
  const coincidencia = /Content Security Policy directive: "([^"]+)"/.exec(mensaje)
  return coincidencia?.[1] ?? null
}
