/**
 * Change 18a, tarea 1.2: ejecuta contra `src/domain/calculo.ts` los casos compartidos de
 * `shared/fixtures/calculo/vta-04-totales.json` cuya entrada declara `"motor": "vta04"`
 * (VTA-04, PRC-22, DSC-05, INV-14, TR-03; `design.md` D13 y D14; `02` §10.4). Mismos casos que
 * corre pytest en `backend/tests/fixtures_compartidos/test_vta04_totales_fixtures.py`.
 */

import { describe, expect, it } from 'vitest'

import { calcularVenta } from '../../../src/domain/calculo'
import type { LineaCalculo } from '../../../src/domain/calculo'
import type { ReglaDescuento } from '../../../src/domain/descuentos/tipos'
import { descubrirCasos } from './cargador'

const casos = descubrirCasos().filter((caso) => caso.entrada['motor'] === 'vta04')

if (casos.length === 0) {
  throw new Error(
    'No se descubrió ningún caso compartido con "motor": "vta04" en ' +
      'shared/fixtures/calculo/ -- el arnés del motor de venta quedaría mudo',
  )
}

// Los valores se pasan tal como vienen del JSON (cadena, nulo o número): el motor rechaza un
// número de punto flotante (INV-03). `unknown` hasta el borde del motor, que lo valida.
type Crudo = Record<string, unknown>

function aLinea(l: Crudo): LineaCalculo {
  return {
    id: l['id'] as string,
    precioReferencia: l['precio_referencia'] as string,
    unidadesReferencia: l['unidades_referencia'] as number,
    cantidadBase: l['cantidad_base'] as number,
    alicuota: l['alicuota'] as string,
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
  const resultado = calcularVenta(
    entrada['modo_impositivo'] as string,
    (entrada['lineas'] as Crudo[]).map(aLinea),
    (entrada['reglas_descuento'] as Crudo[]).map(aRegla),
    entrada['descuento_manual_general'] as string | null,
  )
  return {
    lineas: resultado.lineas.map((linea) => ({
      id: linea.id,
      bruto: linea.bruto.toFixed(2),
      descuento_total: linea.descuentoTotal.toFixed(2),
      neto: linea.neto.toFixed(2),
      alicuota: linea.alicuota.toFixed(6),
      iva: linea.importeIva.toFixed(2),
    })),
    total_neto: resultado.totalNeto.toFixed(2),
    total_iva: resultado.totalIva.toFixed(2),
    total: resultado.total.toFixed(2),
  }
}

/** La comparación de cada caso: lo que calcula el motor debe ser EXACTAMENTE la salida esperada
 * (o fallar con el error que el caso declara). */
function verificar(entrada: Crudo, esperada: unknown): void {
  const salidaEsperada = esperada as { error?: string }

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
}

describe('casos compartidos de VTA-04', () => {
  // Escenarios "Una línea en modo A" (VTA04-una-linea-modo-a-quince-botellas), "La orquestación
  // aplica las reglas que recibe" (VTA04-regla-de-cinco-por-ciento-...), "Modos B y C no
  // soportados" (VTA04-modo-b-... y VTA04-modo-c-...) y "Ambas suites ejecutan los casos": cada
  // caso `vta04` es una prueba identificable por su `id` (ADR-016).
  // Escenario: "Una línea en modo A"
  // Escenario: "La orquestación aplica las reglas que recibe"
  // Escenario: "Modos B y C no soportados"
  it.each(casos.map((caso) => [caso.id, caso] as const))('%s', (_id, caso) => {
    verificar(caso.entrada, caso.salida_esperada)
  })

  // Escenario "Ambas suites ejecutan los casos": el `id` identifica a cada caso sin repetirse y
  // están los de la spec.
  it('los casos vta04 tienen id único y están los de la spec', () => {
    const ids = casos.map((caso) => caso.id)

    expect(new Set(ids).size).toBe(ids.length)
    expect(ids).toEqual(
      expect.arrayContaining([
        'VTA04-una-linea-modo-a-quince-botellas',
        'VTA04-regla-de-cinco-por-ciento-pasa-por-el-motor-de-descuentos',
        'VTA04-modo-b-no-soportado',
        'VTA04-modo-c-no-soportado',
      ]),
    )
  })

  // Escenario "Una divergencia hace fallar CI": un caso `vta04` cuyo total esperado no coincide
  // con lo que calcula el motor falla, y el mismo caso con el total correcto pasa.
  it('una divergencia entre lo esperado y lo calculado hace fallar la suite', () => {
    const caso = casos.find((c) => c.id === 'VTA04-una-linea-modo-a-quince-botellas')
    expect(caso).toBeDefined()
    const esperada = caso!.salida_esperada as Record<string, unknown>

    expect(() => verificar(caso!.entrada, esperada)).not.toThrow()
    expect(() => verificar(caso!.entrada, { ...esperada, total: '31250.01' })).toThrow()
    expect(() =>
      verificar(caso!.entrada, { error: 'MODO_IMPOSITIVO_NO_SOPORTADO' }),
    ).toThrow()
  })
})
