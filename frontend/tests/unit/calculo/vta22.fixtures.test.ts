/**
 * Change 19, tarea 1.3: ejecuta contra `src/domain/ventas/anulacion.ts`
 * los casos compartidos de `shared/fixtures/calculo/vta-22-anulacion.json`
 * cuya entrada declara `"motor": "vta22"` (VTA-21, VTA-22, INV-19; `design.md`
 * D4, D17).
 */

import { describe, expect, it } from 'vitest'

import { efectoEnCuenta } from '../../../src/domain/ventas/anulacion'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'vta22')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "vta22" en ' +
      'shared/fixtures/calculo/ -- el arnés de vta22 quedaría mudo',
  )
}

type Crudo = Record<string, unknown>

describe('casos compartidos de VTA-22', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as Crudo
    const esperada = caso.salida_esperada as {
      movimientos: Array<{ tipo: string; importe: string }>
      saldo_final_relativo: string
    }

    const resultado = efectoEnCuenta(
      entrada['total_venta'] as string,
      (entrada['importe_cobranza'] as string | null) ?? null,
      (entrada['devuelve_dinero'] as boolean | null) ?? null,
    )

    const movimientos = resultado.movimientos.map((m) => ({
      tipo: m.tipo,
      importe: m.importe,
    }))
    expect(movimientos).toEqual(esperada.movimientos)
    expect(resultado.saldoFinalRelativo).toBe(esperada.saldo_final_relativo)
  })
})
