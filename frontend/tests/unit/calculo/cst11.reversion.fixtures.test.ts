/**
 * Change 11, tarea 1.2: ejecuta contra `calcularReversion` de
 * `src/domain/costeo/costoPromedio.ts` los casos de `cst-11-costo-promedio.json` cuya
 * operación es `reversion` (CMP-06, CST-13, `design.md` D9).
 */

import { describe, expect, it } from 'vitest'

import { calcularReversion } from '../../../src/domain/costeo/costoPromedio'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter(
  (caso) => caso.entrada['motor'] === 'cst11' && caso.entrada['operacion'] === 'reversion',
)

if (casos.length === 0) {
  throw new Error('No hay casos de reversión de CST-11 en shared/fixtures/calculo/')
}

interface EntradaReversion {
  stock_previo: number
  promedio_previo: string
  cantidad: number
  costo_ingreso: string
}

describe('casos compartidos de reversión de CST-11 (CMP-06)', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as unknown as EntradaReversion
    const resultado = calcularReversion(
      entrada.stock_previo,
      entrada.promedio_previo,
      entrada.cantidad,
      entrada.costo_ingreso,
    )
    expect({
      promedio_nuevo: resultado.promedioNuevo.toFixed(6),
      stock_nuevo: resultado.stockNuevo,
      recalculado: resultado.recalculado,
    }).toEqual(caso.salida_esperada)
  })
})
