import { describe, expect, it } from 'vitest'

import { generarOperationId } from '../../../src/lib/api/operationId'

/**
 * Tarea 13.1 (`openspec/changes/04-pipeline-comandos/tasks.md`): el cliente
 * necesita un generador de UUIDv7 para el encabezado `Operation-Id` que
 * exige el bus de comandos (`design.md` D4/D7).
 *
 * Formato UUIDv7 (RFC 9562): dígito de versión `7` en la posición 13 y
 * variante (`8`, `9`, `a` o `b`) en la posición 17.
 */
const PATRON_UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

describe('generarOperationId', () => {
  it('devuelve un identificador con formato UUIDv7', () => {
    expect(generarOperationId()).toMatch(PATRON_UUID_V7)
  })

  it('dos llamadas devuelven identificadores distintos (triangulación)', () => {
    const primero = generarOperationId()
    const segundo = generarOperationId()
    expect(primero).not.toBe(segundo)
  })
})
