/**
 * Change 24, tarea 1.3: ejecuta contra `src/domain/stock/rendicion.ts` los casos compartidos de
 * `shared/fixtures/calculo/rut-06-rendicion.json` cuya entrada declara `"motor": "rut06"`
 * (RUT-06, RUT-07, STK-04, INV-04; `design.md` D2, D4). El teléfono y la pantalla de conteo
 * solo calculan `esperado`, `diferencia` y `faltantes`; el conjunto a contar y la validación del
 * conteo son del servidor (`backend/tests/fixtures_compartidos/test_rut06_rendicion.py`).
 */

import { describe, expect, it } from 'vitest'

import {
  calcularDiferencia,
  calcularEsperado,
  productosFaltantes,
} from '../../../src/domain/stock/rendicion'
import { descubrirCasos } from './cargador'

const OPERACIONES_DEL_CLIENTE = ['esperado', 'diferencia', 'faltantes']

const casosDeRut06 = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'rut06')
const casos = casosDeRut06.filter((caso) =>
  OPERACIONES_DEL_CLIENTE.includes(caso.entrada['operacion'] as string),
)

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "rut06" en ' +
      'shared/fixtures/calculo/ -- el arnés de rendicion.ts quedaría mudo',
  )
}

type Crudo = Record<string, unknown>

describe('casos compartidos de RUT-06 y RUT-07', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as Crudo

    switch (entrada['operacion']) {
      case 'esperado':
        expect({
          esperado: calcularEsperado({
            alAbrir: entrada['al_abrir'] as number,
            ingresos: entrada['ingresos'] as number,
            ventas: entrada['ventas'] as number,
            anulaciones: entrada['anulaciones'] as number,
            otros: entrada['otros'] as number,
          }),
        }).toEqual(caso.salida_esperada)
        break
      case 'diferencia':
        expect({
          diferencia: calcularDiferencia(entrada['contada'] as number, entrada['esperada'] as number),
        }).toEqual(caso.salida_esperada)
        break
      case 'faltantes':
        expect({
          faltantes: productosFaltantes(
            entrada['conjunto'] as string[],
            entrada['contados'] as string[],
          ),
        }).toEqual(caso.salida_esperada)
        break
      default:
        throw new Error(`operación no ejecutada por el cliente: ${String(entrada['operacion'])}`)
    }
  })

  it('el cliente ejecuta todas las operaciones que el fixture declara salvo las del servidor', () => {
    const declaradas = new Set(casosDeRut06.map((caso) => caso.entrada['operacion'] as string))
    const delServidor = new Set(['conjunto', 'conteo'])

    for (const operacion of declaradas) {
      expect(OPERACIONES_DEL_CLIENTE.includes(operacion) || delServidor.has(operacion)).toBe(true)
    }
    for (const operacion of OPERACIONES_DEL_CLIENTE) {
      expect(declaradas.has(operacion)).toBe(true)
    }
  })

  it('la diferencia de una línea sin contar todavía no se calcula', () => {
    // La pantalla muestra la diferencia solo cuando hay una cantidad contada entera >= 0.
    expect(calcularDiferencia(null, 40)).toBeNull()
    expect(calcularDiferencia(0, 40)).toBe(-40)
  })
})
