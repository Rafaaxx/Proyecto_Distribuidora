/**
 * Ejecuta contra `src/domain/costeo/costoPromedio.ts` los casos compartidos de
 * `shared/fixtures/calculo/` cuya entrada declara `"motor": "cst11"` (CST-11 y
 * CST-12, `01` §6.2, `02` §10.4, `design.md` D14).
 *
 * ROJO a propósito (change 09, tarea 3.1, grupo 3): `costoPromedio.ts` todavía
 * no existe -- se implementa en la tarea 4.2. Esta suite prueba que el cargador
 * descubre los casos de `cst-11-costo-promedio.json`; la importación inexistente
 * es la evidencia de ROJO. Cada caso es una prueba con su `id`.
 */

import { describe, expect, it } from 'vitest'

import { calcularEgreso, calcularIngreso } from '../../../src/domain/costeo/costoPromedio'
import { descubrirCasos } from './cargador'

// Las operaciones `reversion` (CMP-06, change 11) las ejecuta `cst11.reversion.fixtures.test.ts`.
const casos = descubrirCasos().filter(
  (caso) => caso.entrada['motor'] === 'cst11' && caso.entrada['operacion'] !== 'reversion',
)

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "cst11" en ' +
      'shared/fixtures/calculo/ -- el arnés de costoPromedio.ts quedaría mudo',
  )
}

interface EntradaCst11 {
  operacion: 'ingreso' | 'egreso'
  stock_previo: number
  promedio_previo: string | null
  cantidad: number
  costo_ingreso?: string
}

function ejecutar(entrada: EntradaCst11): Record<string, unknown> {
  if (entrada.operacion === 'ingreso') {
    const ingreso = calcularIngreso(
      entrada.stock_previo,
      entrada.promedio_previo,
      entrada.cantidad,
      entrada.costo_ingreso as string,
    )
    return { promedio_nuevo: ingreso.promedioNuevo.toFixed(6), stock_nuevo: ingreso.stockNuevo }
  }

  const egreso = calcularEgreso(entrada.stock_previo, entrada.promedio_previo, entrada.cantidad)
  return {
    promedio_nuevo: egreso.promedioNuevo === null ? null : egreso.promedioNuevo.toFixed(6),
    stock_nuevo: egreso.stockNuevo,
    costo_valorizacion:
      egreso.costoValorizacion === null ? null : egreso.costoValorizacion.toFixed(6),
  }
}

describe('casos compartidos de CST-11', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as unknown as EntradaCst11
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
