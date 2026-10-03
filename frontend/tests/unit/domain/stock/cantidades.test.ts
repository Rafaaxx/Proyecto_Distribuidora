import { describe, expect, it } from 'vitest'

import {
  aUnidadesBase,
  desdeUnidadesBase,
  formatearCantidad,
  referenciaDePresentaciones,
  referenciaDeRespuesta,
} from '../../../../src/domain/stock/cantidades'

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

describe('formatearCantidad (CAT-08, hallazgo H1: el nombre sale de la presentación)', () => {
  const caja = { unidades: 6, nombre: 'Caja x6' }

  it('unidades base primero y la equivalencia entre paréntesis, con el nombre de la referencia', () => {
    expect(formatearCantidad(60, caja)).toBe('60 unidades (10 Caja x6)')
    expect(formatearCantidad(61, caja)).toBe('61 unidades (10 Caja x6 + 1 un.)')
    expect(formatearCantidad(31, { unidades: 6, nombre: 'Pack x6' })).toBe('31 unidades (5 Pack x6 + 1 un.)')
  })

  it('sin presentaciones enteras se omite el paréntesis', () => {
    expect(formatearCantidad(5, caja)).toBe('5 unidades')
  })

  it('referencia de 1 unidad (Botella) o sin referencia: solo unidades, nunca "cajas"', () => {
    expect(formatearCantidad(24, { unidades: 1, nombre: 'Botella' })).toBe('24 unidades')
    expect(formatearCantidad(24, null)).toBe('24 unidades')
  })

  it('singular y cero', () => {
    expect(formatearCantidad(1, null)).toBe('1 unidad')
    expect(formatearCantidad(1, caja)).toBe('1 unidad')
    expect(formatearCantidad(0, caja)).toBe('0 unidades')
    expect(formatearCantidad(6, caja)).toBe('6 unidades (1 Caja x6)')
  })

  it('un negativo lleva el signo en cada parte: la parte entera con "-" y el resto restando', () => {
    expect(formatearCantidad(-12, caja)).toBe('-12 unidades (-2 Caja x6)')
    expect(formatearCantidad(-13, caja)).toBe('-13 unidades (-2 Caja x6 - 1 un.)')
    expect(formatearCantidad(-1, null)).toBe('-1 unidad')
    expect(formatearCantidad(-5, caja)).toBe('-5 unidades')
  })

  it('sin nombre (la API solo manda las unidades de la referencia) usa un nombre genérico', () => {
    expect(formatearCantidad(61, { unidades: 6, nombre: null })).toBe('61 unidades (10 Presentación x6 + 1 un.)')
  })
})

describe('referencias de presentación', () => {
  it('toma la presentación es_referencia con su nombre', () => {
    const presentaciones = [
      { nombre: 'Botella', unidades_base: 1, es_referencia: false },
      { nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
    ]
    expect(referenciaDePresentaciones(presentaciones)).toEqual({ unidades: 6, nombre: 'Caja x6' })
    expect(referenciaDePresentaciones([presentaciones[0] as (typeof presentaciones)[number]])).toBeNull()
    expect(referenciaDePresentaciones(undefined)).toBeNull()
  })

  it('desde los campos de la respuesta de la API lleva el nombre', () => {
    expect(referenciaDeRespuesta(6, 'Caja x6')).toEqual({ unidades: 6, nombre: 'Caja x6' })
    expect(referenciaDeRespuesta(12, 'Pack x12')).toEqual({ unidades: 12, nombre: 'Pack x12' })
    expect(referenciaDeRespuesta(null, null)).toBeNull()
  })
})
