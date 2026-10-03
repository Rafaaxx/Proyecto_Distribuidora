/**
 * Change 11, tarea 1.1: ejecuta contra `src/domain/compras/calculoCompra.ts` los casos
 * compartidos de `shared/fixtures/calculo/cmp-02-compra.json` cuya entrada declara
 * `"motor": "cmp02"` (CMP-02, `design.md` D5, D15; `02` §10.4). Mismos casos que corre
 * pytest en `backend/tests/fixtures_compartidos/test_cmp02_compra_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import {
  calcularCompra,
  calcularLinea,
  type EntradaDeLinea,
} from '../../../src/domain/compras/calculoCompra'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'cmp02')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "cmp02" en ' +
      'shared/fixtures/calculo/ -- el arnés de calculoCompra.ts quedaría mudo',
  )
}

interface EntradaCmp02 {
  operacion: 'calcular_linea' | 'calcular_compra'
  lineas?: EntradaDeLineaJson[]
}

interface EntradaDeLineaJson {
  unidades_presentacion: number
  cantidad: string
  valor: string
  incluye_iva: boolean
  alicuota: string
  bonificacion: string
}

function aLinea(datos: EntradaDeLineaJson): EntradaDeLinea {
  return {
    unidadesPresentacion: datos.unidades_presentacion,
    cantidad: datos.cantidad,
    valor: datos.valor,
    incluyeIva: datos.incluye_iva,
    alicuota: datos.alicuota,
    bonificacion: datos.bonificacion,
  }
}

function ejecutar(entrada: EntradaCmp02): Record<string, unknown> {
  if (entrada.operacion === 'calcular_linea') {
    const linea = calcularLinea(aLinea(entrada as unknown as EntradaDeLineaJson))
    return {
      cantidad_base: linea.cantidadBase,
      costo_base: linea.costoBase.toFixed(6),
      importe_neto: linea.importeNeto.toFixed(2),
    }
  }
  const totales = calcularCompra((entrada.lineas ?? []).map(aLinea))
  return {
    total_neto: totales.totalNeto.toFixed(2),
    total_factura_sugerido: totales.totalFacturaSugerido.toFixed(2),
  }
}

describe('casos compartidos de CMP-02', () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    const entrada = caso.entrada as unknown as EntradaCmp02
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
