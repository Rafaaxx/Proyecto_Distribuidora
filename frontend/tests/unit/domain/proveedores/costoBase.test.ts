/**
 * `calcularCostoBase` (CST-02, `docs/01-dominio.md` §6.1, tarea 11.1).
 *
 * Los 4 ejemplos de `01` §6.1 y las validaciones (`VALOR_INVALIDO`,
 * `BONIFICACION_INVALIDA`, unidades no enteras/`<1`). Los 14 casos
 * compartidos de `shared/fixtures/calculo/cst-02-costo-base.json` se
 * ejercitan por separado en `tests/unit/calculo/cst02.fixtures.test.ts`.
 */

import { describe, expect, it } from 'vitest'

import {
  BonificacionInvalidaError,
  calcularCostoBase,
  ValorInvalidoError,
} from '../../../../src/domain/proveedores/costoBase'

describe('calcularCostoBase (CST-02)', () => {
  it('caja x12 sin IVA ni bonificación: 18000 / 12 = 1500', () => {
    const resultado = calcularCostoBase('18000.00', false, '0', '0', 12)
    expect(resultado.toFixed(6)).toBe('1500.000000')
  })

  it('caja x12 con IVA 21% incluido: 18000 / 1.21 / 12 = 1239,669421', () => {
    const resultado = calcularCostoBase('18000.00', true, '0.21', '0', 12)
    expect(resultado.toFixed(6)).toBe('1239.669421')
  })

  it('caja x12 con bonificación 10%: 18000 * 0.9 / 12 = 1350', () => {
    const resultado = calcularCostoBase('18000.00', false, '0', '0.10', 12)
    expect(resultado.toFixed(6)).toBe('1350.000000')
  })

  it('botella suelta sin IVA ni bonificación: 1000 / 1 = 1000', () => {
    const resultado = calcularCostoBase('1000.00', false, '0', '0', 1)
    expect(resultado.toFixed(6)).toBe('1000.000000')
  })

  it('valor <= 0 lanza ValorInvalidoError con código VALOR_INVALIDO', () => {
    expect(() => calcularCostoBase('0', false, '0', '0', 12)).toThrow(ValorInvalidoError)
    try {
      calcularCostoBase('-5', false, '0', '0', 12)
      throw new Error('debía lanzar')
    } catch (error) {
      expect(error).toBeInstanceOf(ValorInvalidoError)
      expect((error as ValorInvalidoError).codigo).toBe('VALOR_INVALIDO')
    }
  })

  it('bonificación fuera de [0, 1) lanza BonificacionInvalidaError con código BONIFICACION_INVALIDA', () => {
    expect(() => calcularCostoBase('100', false, '0', '-0.01', 12)).toThrow(
      BonificacionInvalidaError,
    )
    try {
      calcularCostoBase('100', false, '0', '1', 12)
      throw new Error('debía lanzar')
    } catch (error) {
      expect(error).toBeInstanceOf(BonificacionInvalidaError)
      expect((error as BonificacionInvalidaError).codigo).toBe('BONIFICACION_INVALIDA')
    }
  })

  it('un number nativo como valor es rechazado (INV-03)', () => {
    // @ts-expect-error -- la firma exige string; se fuerza para probar la guardia en runtime
    expect(() => calcularCostoBase(18000, false, '0', '0', 12)).toThrow()
  })

  it('unidades no enteras o menores a 1 lanzan Error', () => {
    expect(() => calcularCostoBase('100', false, '0', '0', 1.5)).toThrow()
    expect(() => calcularCostoBase('100', false, '0', '0', 0)).toThrow()
  })
})
