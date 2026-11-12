/**
 * Change 16, tarea 3.1: ejecuta contra `src/domain/descuentos/` los casos compartidos de
 * `shared/fixtures/calculo/dsc-05-descuentos.json` cuya entrada declara `"motor": "dsc05"`
 * (DSC-03, DSC-04, DSC-05, DSC-07, DSC-08; `design.md` D4; `02` §10.4). Mismos casos que corre
 * pytest en `backend/tests/fixtures_compartidos/test_dsc05_descuentos_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import { calcularDescuentos } from '../../../src/domain/descuentos/motor'
import type { LineaVenta, ReglaDescuento } from '../../../src/domain/descuentos/tipos'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'dsc05')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "dsc05" en ' +
      'shared/fixtures/calculo/ -- el arnés del motor de descuentos quedaría mudo',
  )
}

// Los valores se pasan tal como vienen del JSON (cadena, nulo o número): el motor rechaza un
// número de punto flotante (INV-03). `unknown` hasta el borde del motor, que lo valida.
type Crudo = Record<string, unknown>

function aLinea(l: Crudo): LineaVenta {
  return {
    id: l['id'] as string,
    bruto: l['bruto'] as string,
    cantidadBase: l['cantidad_base'] as number,
    unidadesReferencia: l['unidades_referencia'] as number,
    productoId: l['producto_id'] as string,
    categoriaId: l['categoria_id'] as string,
    marcaId: l['marca_id'] as string,
    descuentoManual: l['descuento_manual'] as string | null,
  }
}

function aRegla(r: Crudo): ReglaDescuento {
  return {
    id: r['id'] as string,
    tipo: r['tipo'] as ReglaDescuento['tipo'],
    medida: r['medida'] as ReglaDescuento['medida'],
    operador: r['operador'] as ReglaDescuento['operador'],
    umbral: r['umbral'] as string,
    accionTipo: r['accion_tipo'] as ReglaDescuento['accionTipo'],
    accionPorcentaje: r['accion_porcentaje'] as string | null,
    accionImporte: r['accion_importe'] as string | null,
    acumulable: r['acumulable'] as boolean,
    prioridad: r['prioridad'] as number,
    alcances: (r['alcances'] as Crudo[]).map((a) => ({
      tipo: a['tipo'] as 'PRODUCTO' | 'CATEGORIA' | 'MARCA',
      entidadId: a['entidad_id'] as string,
    })),
  }
}

function ejecutar(entrada: Crudo): Record<string, unknown> {
  const resultado = calcularDescuentos(
    (entrada['lineas'] as Crudo[]).map(aLinea),
    (entrada['reglas_descuento'] as Crudo[]).map(aRegla),
    entrada['descuento_manual_general'] as string | null,
  )
  return {
    lineas: resultado.lineas.map((linea) => ({
      id: linea.id,
      descuentos: linea.descuentos.map((descuento) => ({
        origen: descuento.origen,
        regla_id: descuento.reglaId,
        porcentaje: descuento.porcentaje === null ? null : descuento.porcentaje.toFixed(6),
        importe: descuento.importe.toFixed(2),
      })),
      descuento_total: linea.descuentoTotal.toFixed(2),
      neto: linea.neto.toFixed(2),
    })),
    porcentaje_manual_maximo:
      resultado.porcentajeManualMaximo === null ? null : resultado.porcentajeManualMaximo.toFixed(6),
  }
}

describe('casos compartidos de DSC-05', () => {
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
