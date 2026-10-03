/**
 * Ejecuta contra `src/domain/proveedores/costoBase.ts` los casos
 * compartidos de `shared/fixtures/calculo/` cuya entrada declara
 * `"motor": "cst02"` (CST-02, `02` §10.4, `design.md` D11).
 *
 * ROJO a propósito (change 06, tarea 2.2, grupo 2): `costoBase.ts` todavía
 * no existe -- se implementa recién en la tarea 11.1. Esta suite prueba
 * que el cargador descubre los 14 casos de `cst-02-costo-base.json`; la
 * importación inexistente es la evidencia de ROJO.
 */

import { describe, expect, it } from 'vitest'

import { calcularCostoBase } from '../../../src/domain/proveedores/costoBase'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'cst02')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "cst02" en ' +
      'shared/fixtures/calculo/ -- el arnés de costoBase.ts quedaría mudo',
  )
}

describe('casos compartidos de CST-02', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as {
      valor: string
      incluye_iva: boolean
      computa_credito_fiscal: boolean
      alicuota: string
      bonificacion: string
      unidades: number
    }
    const salidaEsperada = caso.salida_esperada as { error?: boolean; costo_base?: string }

    if (salidaEsperada.error) {
      expect(() =>
        calcularCostoBase(
          entrada.valor,
          entrada.incluye_iva,
          entrada.alicuota,
          entrada.bonificacion,
          entrada.unidades,
          entrada.computa_credito_fiscal,
        ),
      ).toThrow()
      return
    }

    const resultado = calcularCostoBase(
      entrada.valor,
      entrada.incluye_iva,
      entrada.alicuota,
      entrada.bonificacion,
      entrada.unidades,
      entrada.computa_credito_fiscal,
    )
    expect(resultado.toFixed(6)).toBe(salidaEsperada.costo_base)
  })
})
