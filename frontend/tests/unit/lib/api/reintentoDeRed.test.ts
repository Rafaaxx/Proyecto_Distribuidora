import { describe, expect, it } from 'vitest'

import {
  REINTENTOS_POR_ERROR_DE_RED,
  debeReintentar,
  esErrorDeRed,
} from '../../../../src/lib/api/reintentoDeRed'

/**
 * Bug 13.5: `retry: REINTENTOS_POR_ERROR_DE_RED` en
 * `features/proveedores/useMutaciones.ts` y
 * `features/catalogo/useMutacionesCatalogo.ts` reintentaba CUALQUIER
 * rechazo, incluido un 409/422 de dominio que ya tiene una respuesta HTTP
 * real (observado: un nombre duplicado mandaba 3 POST idénticos). Este
 * predicado puro solo autoriza el reintento automático de TanStack Query
 * ante un error de RED (la petición nunca llegó a producir una respuesta
 * HTTP) -- nunca ante un error de dominio ya resuelto por el servidor.
 */
describe('esErrorDeRed (tarea 14.2)', () => {
  it('un error sin `codigo` (falla de fetch en sí, sin respuesta HTTP) es de red', () => {
    expect(esErrorDeRed(new TypeError('Failed to fetch'))).toBe(true)
  })

  it('un error con `codigo` (ya hubo una respuesta HTTP no-ok) no es de red', () => {
    const errorDeDominio = Object.assign(new Error('El nombre ya está en uso.'), {
      codigo: 'NOMBRE_DUPLICADO',
    })
    expect(esErrorDeRed(errorDeDominio)).toBe(false)
  })
})

describe('debeReintentar (tarea 14.2)', () => {
  // TanStack Query llama al predicado con la cantidad de fallos ANTERIORES
  // al actual (0 en el primer fallo), igual que su `retry: n` numérico
  // (`failureCount < n`).
  it('reintenta un error de red mientras no se superen los intentos permitidos', () => {
    expect(debeReintentar(0, new TypeError('Failed to fetch'))).toBe(true)
    expect(debeReintentar(REINTENTOS_POR_ERROR_DE_RED - 1, new TypeError('Failed to fetch'))).toBe(true)
  })

  it('no reintenta un error de red una vez alcanzado el límite', () => {
    expect(debeReintentar(REINTENTOS_POR_ERROR_DE_RED, new TypeError('Failed to fetch'))).toBe(false)
  })

  it('no reintenta un rechazo de dominio (409/422/500 con `codigo`), sin importar los intentos', () => {
    const rechazoDeDominio = Object.assign(new Error('Conflicto.'), { codigo: 'NOMBRE_DUPLICADO' })
    expect(debeReintentar(1, rechazoDeDominio)).toBe(false)

    const errorDeValidacion = Object.assign(new Error('Dato inválido.'), { codigo: 'VALOR_INVALIDO' })
    expect(debeReintentar(1, errorDeValidacion)).toBe(false)

    const errorDeServidor = Object.assign(new Error('Error interno.'), { codigo: 'ERROR_DESCONOCIDO' })
    expect(debeReintentar(1, errorDeServidor)).toBe(false)
  })
})
