import { describe, expect, it } from 'vitest'

import {
  admiteCajas,
  admiteUnidadesSueltas,
  cantidadBaseDeLineas,
  componerLineas,
  excedeElStock,
  type PresentacionDeVenta,
} from '../../../../src/domain/ventas/composicion'

const BOTELLA: PresentacionDeVenta = { presentacionId: 'p-botella', nombre: 'Botella', unidadesBase: 1, esReferencia: false }
const CAJA_X6: PresentacionDeVenta = { presentacionId: 'p-caja', nombre: 'Caja x6', unidadesBase: 6, esReferencia: true }
const PACK_X12: PresentacionDeVenta = { presentacionId: 'p-pack', nombre: 'Pack x12', unidadesBase: 12, esReferencia: false }

/** VTA-02, CAT-07, CAT-08, D8: "cajas + unidades" arma una línea por presentación. */
describe('componerLineas (VTA-02, CAT-07, design D8)', () => {
  it('2 cajas + 3 unidades de Vino A son dos líneas: Caja x6 (12 base) y Botella (3 base)', () => {
    const lineas = componerLineas([BOTELLA, CAJA_X6], 2, 3)
    expect(lineas).toEqual([
      { presentacionId: 'p-caja', nombre: 'Caja x6', cantidad: 2, cantidadBase: 12 },
      { presentacionId: 'p-botella', nombre: 'Botella', cantidad: 3, cantidadBase: 3 },
    ])
    expect(cantidadBaseDeLineas(lineas)).toBe(15)
  })

  it('una parte en cero no genera línea: solo cajas, o solo unidades', () => {
    expect(componerLineas([BOTELLA, CAJA_X6], 5, 0)).toEqual([
      { presentacionId: 'p-caja', nombre: 'Caja x6', cantidad: 5, cantidadBase: 30 },
    ])
    expect(componerLineas([BOTELLA, CAJA_X6], 0, 4)).toEqual([
      { presentacionId: 'p-botella', nombre: 'Botella', cantidad: 4, cantidadBase: 4 },
    ])
    expect(componerLineas([BOTELLA, CAJA_X6], 0, 0)).toEqual([])
  })

  // Escenario: "Unidades sueltas sin presentación de una unidad"
  it('sin presentación de 1 unidad no se ofrecen unidades sueltas (CAT-07) y pedirlas se rechaza', () => {
    expect(admiteUnidadesSueltas([CAJA_X6, PACK_X12])).toBe(false)
    expect(admiteUnidadesSueltas([BOTELLA, CAJA_X6])).toBe(true)
    expect(() => componerLineas([CAJA_X6, PACK_X12], 1, 2)).toThrow(/unidades sueltas/i)
    expect(componerLineas([CAJA_X6, PACK_X12], 1, 0)).toHaveLength(1)
  })

  it('si la referencia es la de 1 unidad hay una sola presentación: cajas y unidades se suman en una línea', () => {
    const solo: PresentacionDeVenta = { presentacionId: 'p-unica', nombre: 'Unidad', unidadesBase: 1, esReferencia: true }
    expect(admiteCajas([solo])).toBe(false)
    expect(componerLineas([solo], 0, 7)).toEqual([{ presentacionId: 'p-unica', nombre: 'Unidad', cantidad: 7, cantidadBase: 7 }])
  })

  it('sin presentación de referencia no hay cajas', () => {
    expect(admiteCajas([BOTELLA, PACK_X12])).toBe(false)
    expect(() => componerLineas([BOTELLA, PACK_X12], 2, 0)).toThrow(/cajas/i)
  })

  it('rechaza cantidades negativas, fraccionarias o que no entran en 32 bits (INV-04)', () => {
    expect(() => componerLineas([BOTELLA, CAJA_X6], -1, 0)).toThrow()
    expect(() => componerLineas([BOTELLA, CAJA_X6], 1.5, 0)).toThrow()
    expect(() => componerLineas([BOTELLA, CAJA_X6], 400_000_000, 0)).toThrow(/32 bits/)
  })
})

describe('excedeElStock (STK-05)', () => {
  it('avisa cuando lo pedido supera el stock conocido', () => {
    expect(excedeElStock(15, 12)).toBe(true)
    expect(excedeElStock(12, 12)).toBe(false)
  })
  it('sin stock conocido (no se pidió ubicación) no avisa', () => {
    expect(excedeElStock(15, null)).toBe(false)
  })
})
