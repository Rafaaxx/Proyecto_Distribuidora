/**
 * Contratos de `src/domain/costeo/costoPromedio.ts` que el formato de los casos
 * compartidos (`cst-11-costo-promedio.json`) no expresa: tipos de entrada,
 * límites y códigos de error (espejo de `backend/tests/unit/test_costeo_domain.py`).
 *
 * Reglas citadas: CST-10, CST-11, CST-12, TR-02, TR-03, INV-03, INV-04.
 */

import { describe, expect, it } from 'vitest'

import {
  CantidadInvalidaError,
  CostoInvalidoError,
  PromedioInconsistenteError,
  STOCK_MAXIMO,
  StockFueraDeRangoError,
  calcularEgreso,
  calcularIngreso,
  validarCosto,
} from '../../../../src/domain/costeo/costoPromedio'

describe('validarCosto (D6)', () => {
  it.each([
    ['1000', '1000.000000'],
    ['1000.5', '1000.500000'],
    ['0.000001', '0.000001'],
    ['999999999999.999999', '999999999999.999999'],
  ])('acepta %s y lo fija a seis decimales', (entrada, esperado) => {
    expect(validarCosto(entrada).toFixed(6)).toBe(esperado)
  })

  it.each([
    '0',
    '0.000000',
    '-1',
    '1000.0000001',
    '1e3',
    'abc',
    '',
    ' 1000',
    '1.000.000',
    '1000000000000.000000',
    'NaN',
    'Infinity',
  ])('rechaza %j con COSTO_INVALIDO', (entrada) => {
    expect(() => validarCosto(entrada)).toThrow(CostoInvalidoError)
    try {
      validarCosto(entrada)
    } catch (error) {
      expect((error as CostoInvalidoError).codigo).toBe('COSTO_INVALIDO')
    }
  })

  it('rechaza un number nativo aunque sea entero (INV-03)', () => {
    expect(() => validarCosto(1000 as unknown as string)).toThrow(CostoInvalidoError)
  })
})

describe('calcularIngreso (CST-11)', () => {
  it('promedia ponderando por el stock total previo', () => {
    const resultado = calcularIngreso(60, '1000.000000', 60, '1100')

    expect(resultado.promedioNuevo.toFixed(6)).toBe('1050.000000')
    expect(resultado.stockNuevo).toBe(120)
  })

  it('triangula con otros valores: (10 x 250 + 30 x 350) / 40', () => {
    const resultado = calcularIngreso(10, '250.000000', 30, '350')

    expect(resultado.promedioNuevo.toFixed(6)).toBe('325.000000')
    expect(resultado.stockNuevo).toBe(40)
  })

  it.each([0, -1, -1000])('con stock previo %i el promedio es el costo del ingreso', (stock) => {
    const resultado = calcularIngreso(stock, '9999.000000', 2000, '12.345678')

    expect(resultado.promedioNuevo.toFixed(6)).toBe('12.345678')
    expect(resultado.stockNuevo).toBe(stock + 2000)
  })

  it('exige el promedio previo con stock previo positivo', () => {
    expect(() => calcularIngreso(5, null, 1, '10')).toThrow(PromedioInconsistenteError)
  })

  it.each([0, -1, 1.5])('rechaza la cantidad %s', (cantidad) => {
    expect(() => calcularIngreso(0, null, cantidad, '10')).toThrow(CantidadInvalidaError)
  })

  it('rechaza un costo inválido antes de calcular', () => {
    expect(() => calcularIngreso(0, null, 1, '0')).toThrow(CostoInvalidoError)
  })

  it('rechaza un stock total que no entra en un entero de 32 bits', () => {
    expect(() => calcularIngreso(STOCK_MAXIMO, '1.000000', 1, '1')).toThrow(StockFueraDeRangoError)
  })

  it('llega exacto al máximo de integer', () => {
    expect(calcularIngreso(STOCK_MAXIMO - 1, '1.000000', 1, '1').stockNuevo).toBe(STOCK_MAXIMO)
  })
})

describe('calcularEgreso (CST-12)', () => {
  it('no cambia el promedio y valoriza a ese promedio', () => {
    const resultado = calcularEgreso(120, '1050.000000', 72)

    expect(resultado.promedioNuevo?.toFixed(6)).toBe('1050.000000')
    expect(resultado.costoValorizacion?.toFixed(6)).toBe('1050.000000')
    expect(resultado.stockNuevo).toBe(48)
  })

  it('triangula: egreso total con otro promedio', () => {
    const resultado = calcularEgreso(5, '12.345678', 5)

    expect(resultado.costoValorizacion?.toFixed(6)).toBe('12.345678')
    expect(resultado.stockNuevo).toBe(0)
  })

  it('sin promedio no valoriza y lo deja nulo (D10)', () => {
    const resultado = calcularEgreso(10, null, 4)

    expect(resultado.promedioNuevo).toBeNull()
    expect(resultado.costoValorizacion).toBeNull()
    expect(resultado.stockNuevo).toBe(6)
  })

  it.each([0, -1])('rechaza la cantidad %i', (cantidad) => {
    expect(() => calcularEgreso(10, null, cantidad)).toThrow(CantidadInvalidaError)
  })

  it('no valida el stock suficiente: eso es de stock', () => {
    expect(calcularEgreso(3, '10.000000', 5).stockNuevo).toBe(-2)
  })
})
