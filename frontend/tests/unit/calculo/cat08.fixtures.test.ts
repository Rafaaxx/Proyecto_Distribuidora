/**
 * Ejecuta contra `src/domain/catalogo/cantidades.ts` los casos compartidos
 * de `shared/fixtures/calculo/` cuya entrada declara `"motor": "cat08"`
 * (CAT-08, `02` §10.4).
 */

import { describe, expect, it } from 'vitest'

import {
  UnidadesDeReferenciaInvalidasError,
  visualizarCantidad,
} from '../../../src/domain/catalogo/cantidades'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'cat08')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "cat08" en ' +
      'shared/fixtures/calculo/ -- el arnés de cantidades.ts quedaría mudo',
  )
}

describe('casos compartidos de CAT-08', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as { cantidad_base: number; unidades_referencia: number }
    const salidaEsperada = caso.salida_esperada as {
      error?: boolean
      cajas?: number
      unidades?: number
      negativo?: boolean
    }

    if (salidaEsperada.error) {
      expect(() =>
        visualizarCantidad(entrada.cantidad_base, entrada.unidades_referencia),
      ).toThrow(UnidadesDeReferenciaInvalidasError)
      return
    }

    const resultado = visualizarCantidad(entrada.cantidad_base, entrada.unidades_referencia)
    expect(resultado.cajas).toBe(salidaEsperada.cajas)
    expect(resultado.unidades).toBe(salidaEsperada.unidades)
    expect(resultado.negativo).toBe(salidaEsperada.negativo)
  })
})
