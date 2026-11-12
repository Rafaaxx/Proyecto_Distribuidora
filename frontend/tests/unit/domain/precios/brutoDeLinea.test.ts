/**
 * Change 13, tarea 3.4: `calcularBrutoDeLinea` (PRC-22, `design.md` D10). Lo que el
 * dispositivo comparte con el servidor corre en `tests/unit/calculo/prc22.fixtures.test.ts`;
 * acá, lo que solo esta implementación puede afirmar: el total no se arma con el precio
 * unitario redondeado, el rechazo de `number` (INV-03) y de cantidades no enteras (INV-04).
 */

import { describe, expect, it } from 'vitest'

import { EntradaNoEsDineroExactoError } from '../../../../src/lib/money'
import {
  ErrorDeBrutoDeLinea,
  calcularBrutoDeLinea,
} from '../../../../src/domain/precios/brutoDeLinea'

describe('calcularBrutoDeLinea', () => {
  it.each([
    ['12500.00', 6, 15, '31250.00'],
    ['8600.00', 6, 3, '4300.00'],
    ['8600.00', 6, 1, '1433.33'],
  ] as const)('%s por %i unidades de referencia, %i base -> %s', (precio, unidades, cantidad, esperado) => {
    expect(calcularBrutoDeLinea(precio, unidades, cantidad).toFixed(2)).toBe(esperado)
  })

  it('no arma el total con el precio unitario redondeado', () => {
    const unitario = calcularBrutoDeLinea('8600.00', 6, 1)

    expect(unitario.times(3).toFixed(2)).toBe('4299.99')
    expect(calcularBrutoDeLinea('8600.00', 6, 3).toFixed(2)).toBe('4300.00')
  })

  it('redondea el medio hacia arriba y no pierde precisión en cocientes periódicos', () => {
    expect(calcularBrutoDeLinea('5.00', 8, 1).toFixed(2)).toBe('0.63')
    expect(calcularBrutoDeLinea('8600.00', 6, 5).toFixed(2)).toBe('7166.67')
    expect(calcularBrutoDeLinea('8600.00', 6, 7).toFixed(2)).toBe('10033.33')
  })

  it('el bruto de n presentaciones es exactamente n por el precio', () => {
    for (const [precio, unidades, n, esperado] of [
      ['12500.00', 6, 2, '25000.00'],
      ['333.33', 7, 3, '999.99'],
      ['0.01', 12, 5, '0.05'],
    ] as const) {
      expect(calcularBrutoDeLinea(precio, unidades, unidades * n).toFixed(2)).toBe(esperado)
    }
  })

  it('INV-03: rechaza un precio number nativo y una cadena que no es un decimal', () => {
    expect(() => calcularBrutoDeLinea(8600 as unknown as string, 6, 1)).toThrow(
      EntradaNoEsDineroExactoError,
    )
    expect(() => calcularBrutoDeLinea('ocho mil', 6, 1)).toThrow(EntradaNoEsDineroExactoError)
  })

  it.each([0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])(
    'INV-04: rechaza la cantidad base %s',
    (cantidad) => {
      expect(() => calcularBrutoDeLinea('8600.00', 6, cantidad)).toThrow(ErrorDeBrutoDeLinea)
      try {
        calcularBrutoDeLinea('8600.00', 6, cantidad)
      } catch (error) {
        expect((error as ErrorDeBrutoDeLinea).codigo).toBe('CANTIDAD_BASE_INVALIDA')
      }
    },
  )

  it.each([0, -6, 6.5, Number.NaN])('INV-04: rechaza las unidades de referencia %s', (unidades) => {
    try {
      calcularBrutoDeLinea('8600.00', unidades, 3)
      expect.unreachable('debía rechazar las unidades de referencia')
    } catch (error) {
      expect((error as ErrorDeBrutoDeLinea).codigo).toBe('UNIDADES_REFERENCIA_INVALIDAS')
    }
  })
})
