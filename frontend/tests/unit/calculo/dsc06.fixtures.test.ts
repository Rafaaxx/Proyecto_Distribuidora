/**
 * Change 16, tarea 12.3: ejecuta contra `src/domain/descuentos/manual.ts` los casos compartidos de
 * `shared/fixtures/calculo/dsc-06-descuento-manual.json` cuya entrada declara `"motor": "dsc06"`
 * (DSC-06, TR-02, INV-03; `design.md` D4, D12; `02` §10.4). Mismos casos que corre pytest en
 * `backend/tests/fixtures_compartidos/test_dsc06_descuento_manual_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import { evaluarDescuentoManual } from '../../../src/domain/descuentos/manual'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'dsc06')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "dsc06" en ' +
      'shared/fixtures/calculo/ -- el arnés del descuento manual quedaría mudo',
  )
}

// Los valores se pasan tal como vienen del JSON (cadena, nulo o número): la evaluación rechaza un
// número de punto flotante (INV-03).
type Crudo = Record<string, unknown>

function ejecutar(entrada: Crudo): Record<string, unknown> {
  const autorizador = entrada['autorizador'] as Crudo | null
  const resultado = evaluarDescuentoManual({
    usuarioId: entrada['usuario_id'] as string,
    descuentoManualHabilitado: entrada['descuento_manual_habilitado'] as boolean,
    motivoObligatorio: entrada['motivo_obligatorio'] as boolean | null,
    permisosUsuario: entrada['permisos_usuario'] as string[],
    topeRol: entrada['tope_rol'] as string,
    topePropio: entrada['tope_propio'] as string | null,
    porcentajeMaximo: entrada['porcentaje_maximo'] as string,
    motivo: entrada['motivo'] as string | null,
    autorizador:
      autorizador === null
        ? null
        : {
            usuarioId: autorizador['usuario_id'] as string,
            permisos: autorizador['permisos'] as string[],
          },
  })
  return {
    tope_aplicado: resultado.topeAplicado.toFixed(6),
    requirio_autorizacion: resultado.requirioAutorizacion,
    resolucion: resultado.resolucion,
    autorizador_id: resultado.autorizadorId,
  }
}

describe('casos compartidos de DSC-06', () => {
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
})
