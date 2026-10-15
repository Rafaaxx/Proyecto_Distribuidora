/**
 * Change 16, tarea 3.1: condición de volumen (DSC-02, DSC-03, INV-04; `design.md` D5, D6). Lo que
 * comparte con el servidor corre en `tests/unit/calculo/dsc05.fixtures.test.ts`; acá, la
 * aritmética racional exacta de las cajas equivalentes.
 */

import { describe, expect, it } from 'vitest'

import {
  compararRacionales,
  cumpleCondicion,
  lineasElegibles,
  medir,
  racional,
} from '../../../../src/domain/descuentos/condicion'
import type {
  AlcanceRegla,
  LineaVenta,
  ReglaDescuento,
} from '../../../../src/domain/descuentos/tipos'

function linea(id: string, parcial: Partial<LineaVenta> = {}): LineaVenta {
  return {
    id,
    bruto: '100.00',
    cantidadBase: 1,
    unidadesReferencia: 1,
    productoId: 'p1',
    categoriaId: 'c1',
    marcaId: 'm1',
    descuentoManual: null,
    ...parcial,
  }
}

function regla(parcial: Partial<ReglaDescuento> = {}): ReglaDescuento {
  return {
    id: 'r1',
    tipo: 'VOLUMEN_OPERACION',
    medida: 'UNIDADES_BASE',
    operador: 'GTE',
    umbral: '1',
    accionTipo: 'PORCENTAJE',
    accionPorcentaje: '0.050000',
    accionImporte: null,
    acumulable: false,
    prioridad: 1,
    alcances: [],
    ...parcial,
  }
}

const ids = (lineas: readonly LineaVenta[]): string[] => lineas.map((l) => l.id)

describe('lineasElegibles', () => {
  it('una regla de operación toma todas las líneas', () => {
    const lineas = [linea('a'), linea('b', { productoId: 'p2' })]
    expect(ids(lineasElegibles(regla(), lineas))).toEqual(['a', 'b'])
  })

  it('una regla de alcance toma la unión de producto, categoría y marca', () => {
    const alcances: AlcanceRegla[] = [
      { tipo: 'CATEGORIA', entidadId: 'vinos' },
      { tipo: 'MARCA', entidadId: 'sur' },
    ]
    const lineas = [
      linea('vino', { categoriaId: 'vinos', marcaId: 'otra' }),
      linea('cerveza', { categoriaId: 'cervezas', marcaId: 'sur' }),
      linea('alfajor', { categoriaId: 'golosinas', marcaId: 'dulce' }),
    ]
    expect(ids(lineasElegibles(regla({ tipo: 'VOLUMEN_ALCANCE', alcances }), lineas))).toEqual([
      'vino',
      'cerveza',
    ])
  })

  it('un alcance de un tipo no se confunde con otro tipo', () => {
    const alcances: AlcanceRegla[] = [{ tipo: 'MARCA', entidadId: 'x' }]
    const elegibles = lineasElegibles(
      regla({ tipo: 'VOLUMEN_ALCANCE', alcances }),
      [linea('a', { productoId: 'x' })],
    )
    expect(elegibles).toEqual([])
  })
})

describe('medir', () => {
  it('unidades base suma las cantidades', () => {
    const m = medir('UNIDADES_BASE', [linea('a', { cantidadBase: 60 }), linea('b', { cantidadBase: 5 })])
    expect(compararRacionales(m, racional(65n, 1n))).toBe(0)
  })

  it('importe bruto suma los brutos exactos', () => {
    const m = medir('IMPORTE_BRUTO', [linea('a', { bruto: '31250.00' }), linea('b', { bruto: '0.01' })])
    expect(compararRacionales(m, racional(3125001n, 100n))).toBe(0)
  })

  it('19 cajas y 5 unidades de una caja x6 son 119/6', () => {
    const m = medir('CAJAS_EQUIVALENTES', [
      linea('a', { cantidadBase: 114, unidadesReferencia: 6 }),
      linea('b', { cantidadBase: 5, unidadesReferencia: 6 }),
    ])
    expect(compararRacionales(m, racional(119n, 6n))).toBe(0)
  })

  it('suma cajas de distinto tamaño: 3/6 + 6/12 = 1', () => {
    const m = medir('CAJAS_EQUIVALENTES', [
      linea('a', { cantidadBase: 3, unidadesReferencia: 6 }),
      linea('b', { cantidadBase: 6, unidadesReferencia: 12 }),
    ])
    expect(compararRacionales(m, racional(1n, 1n))).toBe(0)
  })

  it('tres tercios de caja suman exactamente uno', () => {
    const tercios = ['a', 'b', 'c'].map((id) =>
      linea(id, { cantidadBase: 2, unidadesReferencia: 6 }),
    )
    expect(compararRacionales(medir('CAJAS_EQUIVALENTES', tercios), racional(1n, 1n))).toBe(0)
  })
})

describe('cumpleCondicion', () => {
  it.each([
    ['GTE', 120, true],
    ['GTE', 119, false],
    ['GT', 120, false],
    ['GT', 126, true],
  ] as const)('cajas equivalentes %s 20 con %i unidades base de una caja x6 -> %s', (operador, cantidad, esperado) => {
    const r = regla({ medida: 'CAJAS_EQUIVALENTES', operador, umbral: '20' })
    expect(cumpleCondicion(r, [linea('a', { cantidadBase: cantidad, unidadesReferencia: 6 })])).toBe(
      esperado,
    )
  })

  it('tres tercios cumplen "≥ 1" pero no "> 1"', () => {
    const tercios = ['a', 'b', 'c'].map((id) =>
      linea(id, { cantidadBase: 2, unidadesReferencia: 6 }),
    )
    expect(cumpleCondicion(regla({ medida: 'CAJAS_EQUIVALENTES', umbral: '1' }), tercios)).toBe(true)
    expect(
      cumpleCondicion(regla({ medida: 'CAJAS_EQUIVALENTES', operador: 'GT', umbral: '1' }), tercios),
    ).toBe(false)
  })

  it('un umbral de cuatro decimales se compara exacto: 1/3 alcanza 0,3333 pero no 0,3334', () => {
    const lineas = [linea('a', { cantidadBase: 2, unidadesReferencia: 6 })]
    expect(cumpleCondicion(regla({ medida: 'CAJAS_EQUIVALENTES', umbral: '0.3333' }), lineas)).toBe(true)
    expect(cumpleCondicion(regla({ medida: 'CAJAS_EQUIVALENTES', umbral: '0.3334' }), lineas)).toBe(false)
  })

  it.each([
    ['GTE', '31250', true],
    ['GT', '31250', false],
    ['GTE', '31250.01', false],
  ] as const)('importe bruto %s %s con 31250.00 -> %s', (operador, umbral, esperado) => {
    const r = regla({ medida: 'IMPORTE_BRUTO', operador, umbral })
    expect(cumpleCondicion(r, [linea('a', { bruto: '31250.00' })])).toBe(esperado)
  })

  it('una regla de alcance mide solo sus líneas', () => {
    const r = regla({
      tipo: 'VOLUMEN_ALCANCE',
      medida: 'CAJAS_EQUIVALENTES',
      umbral: '10',
      alcances: [{ tipo: 'PRODUCTO', entidadId: 'pa' }],
    })
    const lineas = [
      linea('a', { productoId: 'pa', cantidadBase: 48, unidadesReferencia: 6 }),
      linea('b', { productoId: 'pb', cantidadBase: 60, unidadesReferencia: 6 }),
    ]
    expect(cumpleCondicion(r, lineas)).toBe(false)
  })

  it('una regla sin líneas elegibles no aplica aunque el umbral sea cero', () => {
    const r = regla({
      tipo: 'VOLUMEN_ALCANCE',
      umbral: '0',
      alcances: [{ tipo: 'PRODUCTO', entidadId: 'no-esta' }],
    })
    expect(cumpleCondicion(r, [linea('a')])).toBe(false)
  })
})
