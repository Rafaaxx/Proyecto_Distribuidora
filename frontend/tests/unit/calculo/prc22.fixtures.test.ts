/**
 * Change 13, tarea 3.2: ejecuta contra `src/domain/precios/brutoDeLinea.ts` los casos
 * compartidos de `shared/fixtures/calculo/prc-22-bruto-de-linea.json` cuya entrada declara
 * `"motor": "prc22"` (PRC-22, `design.md` D10; `02` §10.4). Mismos casos que corre pytest
 * en `backend/tests/fixtures_compartidos/test_prc22_bruto_de_linea_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import { calcularBrutoDeLinea } from '../../../src/domain/precios/brutoDeLinea'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'prc22')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "prc22" en ' +
      'shared/fixtures/calculo/ -- el arnés de brutoDeLinea.ts quedaría mudo',
  )
}

interface EntradaPrc22 {
  precio_referencia: string
  unidades_referencia: number
  cantidad_base: number
}

function ejecutar(entrada: EntradaPrc22): Record<string, unknown> {
  const bruto = calcularBrutoDeLinea(
    entrada.precio_referencia,
    entrada.unidades_referencia,
    entrada.cantidad_base,
  )
  return { bruto: bruto.toFixed(2) }
}

describe('casos compartidos de PRC-22', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as unknown as EntradaPrc22
    const salidaEsperada = caso.salida_esperada as { error?: string }

    if (salidaEsperada.error !== undefined) {
      let capturado: unknown
      try {
        ejecutar(entrada)
      } catch (error) {
        capturado = error
      }
      expect(capturado).toBeDefined()
      expect((capturado as { codigo?: string }).codigo).toBe(salidaEsperada.error)
      return
    }

    expect(ejecutar(entrada)).toEqual(salidaEsperada)
  })
})
