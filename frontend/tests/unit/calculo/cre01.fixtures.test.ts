/**
 * Change 18b, tarea 1.3: ejecuta contra `src/domain/credito/evaluacion.ts` los casos compartidos
 * de `shared/fixtures/calculo/cre-01-credito.json` cuya entrada declara `"motor": "cre01"`
 * (CRE-01 a CRE-07, ADR-032, TR-03, INV-03; `design.md` D5, D6, D8; `02` §10.4). Mismos casos que
 * corre pytest en `backend/tests/fixtures_compartidos/test_cre01_credito_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import { evaluarCredito } from '../../../src/domain/credito/evaluacion'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'cre01')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "cre01" en ' +
      'shared/fixtures/calculo/ -- el arnés del motor de crédito quedaría mudo',
  )
}

// Los valores se pasan tal como vienen del JSON (cadena, nulo o número): el motor rechaza un
// número de punto flotante (INV-03).
type Crudo = Record<string, unknown>

function ejecutar(entrada: Crudo): Record<string, unknown> {
  const autorizador = entrada['autorizador'] as Crudo | null
  const resultado = evaluarCredito({
    limite: entrada['limite'] as string | null,
    saldoActual: entrada['saldo_actual'] as string,
    totalVenta: entrada['total_venta'] as string,
    cobranza: entrada['cobranza'] as string,
    politica: entrada['politica'] as string,
    toleranciaTipo: entrada['tolerancia_tipo'] as string | null,
    toleranciaValor: entrada['tolerancia_valor'] as string | null,
    modo: entrada['modo'] as string,
    aceptaExceso: entrada['acepta_exceso'] as boolean,
    usuarioId: entrada['usuario_id'] as string,
    permisosUsuario: entrada['permisos_usuario'] as string[],
    autorizador:
      autorizador === null
        ? null
        : {
            usuarioId: autorizador['usuario_id'] as string,
            permisos: autorizador['permisos'] as string[],
          },
  })
  return {
    disponible: resultado.disponible === null ? null : resultado.disponible.toFixed(2),
    saldo_resultante: resultado.saldoResultante.toFixed(2),
    exceso: resultado.exceso.toFixed(2),
    tolerancia: resultado.tolerancia.toFixed(2),
    resolucion: resultado.resolucion,
    autorizador_id: resultado.autorizadorId,
  }
}

describe('casos compartidos de CRE-01', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const salidaEsperada = caso.salida_esperada as { error?: string }

    if (salidaEsperada.error !== undefined) {
      let capturado: unknown
      try {
        ejecutar(caso.entrada)
      } catch (error) {
        capturado = error
      }
      expect(capturado).toBeDefined()
      expect((capturado as { codigo?: string }).codigo).toBe(salidaEsperada.error)
      return
    }

    expect(ejecutar(caso.entrada)).toEqual(salidaEsperada)
  })

  // Escenario "Los casos compartidos corren en las dos suites": el `id` identifica a cada caso sin
  // repetirse y las reglas de la spec están citadas.
  it('los casos cre01 tienen id único y citan las reglas de la spec', () => {
    const ids = casos.map((caso) => caso.id)
    const citadas = new Set(casos.flatMap((caso) => caso.reglas))

    expect(new Set(ids).size).toBe(ids.length)
    for (const regla of [
      'CRE-01',
      'CRE-02',
      'CRE-03',
      'CRE-04',
      'CRE-05',
      'CRE-06',
      'CRE-07',
      'ADR-032',
      'TR-03',
      'INV-03',
    ]) {
      expect(citadas.has(regla)).toBe(true)
    }
  })
})
