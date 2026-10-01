import { describe, expect, it } from 'vitest'

import { aUnidadesBase, desdeUnidadesBase, formatearCantidad } from '../../../../src/domain/stock/cantidades'

/** CAT-08 e INV-04: las cantidades viajan en unidad base entera; la pantalla las
 * escribe y las muestra en cajas + unidades con aritmética entera. */
describe('aUnidadesBase', () => {
  it('convierte cajas y unidades con la presentación de referencia', () => {
    expect(aUnidadesBase(5, 1, 6)).toBe(31)
    expect(aUnidadesBase(0, 4, 6)).toBe(4)
    expect(aUnidadesBase(2, 0, 12)).toBe(24)
  })

  it('sin presentación de referencia solo cuentan las unidades', () => {
    expect(aUnidadesBase(0, 7, null)).toBe(7)
  })

  it.each([
    [1.5, 0],
    [0, 2.5],
    [-1, 0],
    [0, -1],
    [Number.NaN, 0],
  ])('rechaza cajas=%s unidades=%s que no son enteros no negativos', (cajas, unidades) => {
    expect(() => aUnidadesBase(cajas, unidades, 6)).toThrow()
  })

  it('rechaza un resultado que no entra en un entero de 32 bits', () => {
    expect(() => aUnidadesBase(2_147_483_647, 1, 6)).toThrow()
  })
})

describe('desdeUnidadesBase', () => {
  it('reparte en cajas y unidades', () => {
    expect(desdeUnidadesBase(31, 6)).toEqual({ cajas: 5, unidades: 1 })
    expect(desdeUnidadesBase(12, 6)).toEqual({ cajas: 2, unidades: 0 })
    expect(desdeUnidadesBase(4, 6)).toEqual({ cajas: 0, unidades: 4 })
  })

  it('un negativo conserva el signo en la parte que corresponde', () => {
    expect(desdeUnidadesBase(-31, 6)).toEqual({ cajas: -5, unidades: -1 })
  })

  it('sin referencia todo son unidades', () => {
    expect(desdeUnidadesBase(31, null)).toEqual({ cajas: 0, unidades: 31 })
  })
})

describe('formatearCantidad', () => {
  it('muestra cajas + unidades', () => {
    expect(formatearCantidad(31, 6)).toBe('5 cajas + 1 un.')
    expect(formatearCantidad(12, 6)).toBe('2 cajas')
    expect(formatearCantidad(1, 1)).toBe('1 caja')
    expect(formatearCantidad(4, 6)).toBe('4 un.')
  })

  it('sin referencia o cantidad cero', () => {
    expect(formatearCantidad(31, null)).toBe('31 un.')
    expect(formatearCantidad(0, 6)).toBe('0 un.')
  })

  it('un negativo se marca en cada parte', () => {
    expect(formatearCantidad(-31, 6)).toBe('-5 cajas + -1 un.')
  })
})
