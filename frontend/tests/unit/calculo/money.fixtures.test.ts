/**
 * Ejecuta contra `src/lib/money.ts` los casos compartidos de
 * `shared/fixtures/calculo/` cuya entrada declara `"motor": "money"`.
 *
 * Spec `calculo-compartido`: cada caso compartido es una prueba
 * identificable en ambas suites, con el `id` del caso en el nombre de la
 * prueba (Python y TypeScript comparan la misma representación decimal
 * exacta, sin tolerancia numérica).
 */

import { describe, expect, it } from 'vitest'

import { redondearCosto, redondearImporte } from '../../../src/lib/money'
import { descubrirCasos } from './cargador'

const OPERACIONES: Record<string, (valor: string) => { toFixed(n: number): string }> = {
  redondear_importe: redondearImporte,
  redondear_costo: redondearCosto,
}

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'money')

// Guardia de deriva: si el fixture semilla dejara de tener casos de `money`,
// esta suite no debe quedar en silencio con 0 pruebas.
if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "money" en ' +
      'shared/fixtures/calculo/ -- el arnés de money.ts quedaría mudo',
  )
}

describe('casos compartidos de money', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as { operacion: string; valor: string }
    const operacion = OPERACIONES[entrada.operacion]
    if (!operacion) {
      throw new Error(`Operación desconocida en el caso ${caso.id}: ${entrada.operacion}`)
    }

    const esperado = (caso.salida_esperada as { resultado: string }).resultado
    const decimales = esperado.includes('.') ? esperado.split('.')[1]!.length : 0

    const resultado = operacion(entrada.valor)

    expect(resultado.toFixed(decimales)).toBe(esperado)
  })
})
