/**
 * Change 16, tarea 3.1: acciones de una regla de descuento (DSC-04, DSC-07, TR-03, INV-03;
 * `design.md` D10). Redondeo solo desde `lib/money.ts`; nada se convierte a `number`.
 */

import { describe, expect, it } from 'vitest'

import { descuentoPorcentual, repartirImporteFijo } from '../../../../src/domain/descuentos/acciones'
import { EntradaNoEsDineroExactoError, parsearImporteDesdeApi } from '../../../../src/lib/money'

const importes = (...valores: string[]) => valores.map((v) => parsearImporteDesdeApi(v))
const texto = (valores: readonly { toFixed(n: number): string }[]) => valores.map((v) => v.toFixed(2))

describe('descuentoPorcentual', () => {
  it('redondea por línea con mitad hacia arriba: 5% de 1433.33 = 71.67', () => {
    expect(texto(descuentoPorcentual(importes('1433.33'), '0.05'))).toEqual(['71.67'])
  })

  it('redondea línea por línea, no sobre el total: 71.67 + 71.67, no 143.33', () => {
    expect(texto(descuentoPorcentual(importes('1433.33', '1433.33'), '0.05'))).toEqual([
      '71.67',
      '71.67',
    ])
  })

  it('cinco por ciento sobre 250000.00', () => {
    expect(texto(descuentoPorcentual(importes('250000.00'), '0.050000'))).toEqual(['12500.00'])
  })

  it('un descuento que redondea a cero devuelve 0.00', () => {
    expect(texto(descuentoPorcentual(importes('0.05'), '0.05'))).toEqual(['0.00'])
  })

  it('cien por ciento deja el neto en cero', () => {
    expect(texto(descuentoPorcentual(importes('4300.00'), '1'))).toEqual(['4300.00'])
  })

  it('un porcentaje number se rechaza (INV-03)', () => {
    expect(() => descuentoPorcentual(importes('100.00'), 0.05 as unknown as string)).toThrow(
      EntradaNoEsDineroExactoError,
    )
  })
})

describe('repartirImporteFijo', () => {
  it('reparto proporcional sin remanente', () => {
    expect(texto(repartirImporteFijo(importes('31250.00', '4300.00'), '1000.00'))).toEqual([
      '879.04',
      '120.96',
    ])
  })

  it('el remanente negativo va a la línea de mayor importe', () => {
    const partes = repartirImporteFijo(importes('31250.00', '4300.00', '1433.33'), '1000.00')
    expect(texto(partes)).toEqual(['844.97', '116.27', '38.76'])
    expect(partes.reduce((suma, parte) => suma.plus(parte)).toFixed(2)).toBe('1000.00')
  })

  it('el remanente va a la mayor aunque no sea la primera', () => {
    expect(
      texto(repartirImporteFijo(importes('1433.33', '4300.00', '31250.00'), '1000.00')),
    ).toEqual(['38.76', '116.27', '844.97'])
  })

  it('el remanente positivo con empate va a la primera línea', () => {
    expect(
      texto(repartirImporteFijo(importes('8600.00', '8600.00', '8600.00'), '100.00')),
    ).toEqual(['33.34', '33.33', '33.33'])
  })

  it('un importe mayor que la suma se topa en la suma', () => {
    expect(texto(repartirImporteFijo(importes('4300.00'), '5000.00'))).toEqual(['4300.00'])
    expect(texto(repartirImporteFijo(importes('100.00', '50.00'), '1000.00'))).toEqual([
      '100.00',
      '50.00',
    ])
  })

  it('sobre importes en cero no descuenta nada', () => {
    expect(texto(repartirImporteFijo(importes('0.00', '0.00'), '10.00'))).toEqual(['0.00', '0.00'])
  })

  it('un importe fijo number se rechaza (INV-03)', () => {
    expect(() => repartirImporteFijo(importes('100.00'), 10.5 as unknown as string)).toThrow(
      EntradaNoEsDineroExactoError,
    )
  })
})
