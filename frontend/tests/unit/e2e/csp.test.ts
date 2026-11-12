/**
 * Change 28, tarea 6.2 (D9, D14): el detector de violaciones de la política de seguridad de
 * contenido que usa la suite de aceptación (`tests/e2e/apoyo/csp.ts`). Spec
 * `sistema/aceptacion-etapa-1`, requisito «La suite no tolera errores de seguridad del
 * navegador». Regla: `02` §18.
 */
import { describe, expect, it } from 'vitest'

import { directivaViolada, esViolacionDeCsp } from '../../e2e/apoyo/csp'

const SCRIPT_BLOQUEADO =
  "Refused to execute inline script because it violates the following Content Security Policy directive: \"script-src 'self'\". Either the 'unsafe-inline' keyword is required."
const IMAGEN_BLOQUEADA =
  "Refused to load the image 'data:image/png;base64,AAA' because it violates the following Content Security Policy directive: \"img-src 'none'\"."
const EVAL_BLOQUEADO =
  "Refused to evaluate a string as JavaScript because 'unsafe-eval' is not an allowed source of script in the following Content Security Policy directive: \"script-src 'self'\"."

// Redacción de las versiones recientes de Chromium (la que informa Playwright 1.64).
const SCRIPT_EXTERNO =
  "Loading the script 'https://origen-no-permitido.invalid/x.js' violates the following Content Security Policy directive: \"script-src 'self'\". Note that 'script-src-elem' was not explicitly set, so 'script-src' is used as a fallback. The action has been blocked."

describe('esViolacionDeCsp', () => {
  it('reconoce la redacción de las versiones recientes de Chromium', () => {
    expect(esViolacionDeCsp(SCRIPT_EXTERNO)).toBe(true)
    expect(directivaViolada(SCRIPT_EXTERNO)).toBe("script-src 'self'")
  })

  it('reconoce los mensajes de Chromium que informan una violación', () => {
    expect(esViolacionDeCsp(SCRIPT_BLOQUEADO)).toBe(true)
    expect(esViolacionDeCsp(IMAGEN_BLOQUEADA)).toBe(true)
    expect(esViolacionDeCsp(EVAL_BLOQUEADO)).toBe(true)
  })

  it('no confunde otros mensajes de la consola', () => {
    expect(esViolacionDeCsp('Failed to load resource: the server responded with a status of 401')).toBe(false)
    expect(esViolacionDeCsp('Service worker registrado')).toBe(false)
    expect(esViolacionDeCsp('')).toBe(false)
  })
})

describe('directivaViolada', () => {
  it('extrae la directiva nombrada en el mensaje', () => {
    expect(directivaViolada(SCRIPT_BLOQUEADO)).toBe("script-src 'self'")
    expect(directivaViolada(IMAGEN_BLOQUEADA)).toBe("img-src 'none'")
    expect(directivaViolada(EVAL_BLOQUEADO)).toBe("script-src 'self'")
  })

  it('devuelve null si el mensaje no nombra una directiva', () => {
    expect(directivaViolada('otro mensaje')).toBeNull()
  })
})
