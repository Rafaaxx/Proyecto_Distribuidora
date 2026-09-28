import { describe, expect, it } from 'vitest'

import {
  EntradaNoEsDineroExactoError,
  formatearCosto,
  formatearImporte,
  formatearPorcentaje,
  parsearImporteDesdeApi,
  redondearCosto,
  redondearImporte,
} from '../../../src/lib/money'

describe('redondearImporte', () => {
  it('desempata el medio positivo hacia arriba (ROUND_HALF_UP)', () => {
    expect(redondearImporte('0.125').toString()).toBe('0.13')
  })

  it('desempata el medio negativo alejándose de cero', () => {
    expect(redondearImporte('-0.125').toString()).toBe('-0.13')
  })

  it('el resultado tiene exactamente dos decimales', () => {
    expect(redondearImporte('10').toFixed(2)).toBe('10.00')
  })

  it('rechaza un number nativo con un error explícito', () => {
    expect(() => redondearImporte(0.125 as unknown as string)).toThrow(
      EntradaNoEsDineroExactoError,
    )
  })

  it('rechaza una cadena que no es un número', () => {
    expect(() => redondearImporte('abc')).toThrow(EntradaNoEsDineroExactoError)
  })
})

describe('redondearCosto', () => {
  it('cuantiza a seis decimales con medio hacia arriba', () => {
    expect(redondearCosto('1.0000005').toFixed(6)).toBe('1.000001')
  })

  it('representa la alícuota de IVA del 21% como 0.210000', () => {
    expect(redondearCosto('0.21').toFixed(6)).toBe('0.210000')
  })

  it('rechaza un number nativo con un error explícito', () => {
    expect(() => redondearCosto(1.0000005 as unknown as string)).toThrow(
      EntradaNoEsDineroExactoError,
    )
  })
})

describe('parsearImporteDesdeApi', () => {
  it('convierte la cadena de la API en un decimal exacto sin pasar por number', () => {
    const importe = parsearImporteDesdeApi('31250.00')

    expect(importe.toString()).toBe('31250')
    expect(redondearImporte(importe.toString()).toFixed(2)).toBe('31250.00')
  })
})

describe('formatearImporte', () => {
  it('agrupa miles con "." y usa "," como separador decimal', () => {
    expect(formatearImporte(redondearImporte('31250'))).toBe('31.250,00')
  })

  it('cero se muestra con dos decimales', () => {
    expect(formatearImporte(redondearImporte('0'))).toBe('0,00')
  })

  it('un negativo conserva el signo delante del entero', () => {
    expect(formatearImporte(redondearImporte('-1234.5'))).toBe('-1.234,50')
  })

  it('formatea sin separador de miles cuando la parte entera tiene menos de 4 dígitos', () => {
    expect(formatearImporte(redondearImporte('833'))).toBe('833,00')
  })

  it('agrupa miles en un importe de cinco dígitos', () => {
    expect(formatearImporte(redondearImporte('18000'))).toBe('18.000,00')
  })

  it('agrupa miles en valores de millones', () => {
    expect(formatearImporte(redondearImporte('1234567.89'))).toBe('1.234.567,89')
  })
})

/**
 * Tarea 11.4: vista previa del costo base en la pantalla de carga
 * (`administracion-de-proveedores`, escenarios "Vista previa de una caja
 * con IVA" y "Bonificación en porcentaje"): separador de miles `.` y
 * decimal `,` (es-AR), seis decimales fijos. Manipulación de cadenas sobre
 * el resultado ya redondeado -- nunca pasa por `number` (INV-03).
 */
describe('formatearCosto', () => {
  it('agrupa miles con "." y usa "," como separador decimal (CST-02 ejemplo 3)', () => {
    expect(formatearCosto(redondearCosto('1239.669421'))).toBe('1.239,669421')
  })

  it('formatea sin separador de miles cuando la parte entera tiene menos de 4 dígitos (CST-02 ejemplo 4)', () => {
    expect(formatearCosto(redondearCosto('1350'))).toBe('1.350,000000')
  })

  it('un valor sin parte entera de miles no agrega el separador', () => {
    expect(formatearCosto(redondearCosto('833.333333'))).toBe('833,333333')
  })

  it('siempre muestra seis decimales, incluso en cero', () => {
    expect(formatearCosto(redondearCosto('1500'))).toBe('1.500,000000')
  })

  it('un negativo conserva el signo delante del entero', () => {
    expect(formatearCosto(redondearCosto('-1239.669421'))).toBe('-1.239,669421')
  })
})

/**
 * Change 06, tarea 14.5 (corrección de la verificación manual 13.5): la
 * pantalla de historial mostraba `alicuota_aplicada` con `formatearCosto`
 * ("0,210000"), pero es una fracción (TR-02) que se muestra como
 * porcentaje. Nunca pasa por `number` -- multiplica con decimal.js y
 * manipula el resultado como cadena, igual criterio que `formatearCosto`.
 */
describe('formatearPorcentaje', () => {
  it('una fracción entera se muestra sin decimales (21 %)', () => {
    expect(formatearPorcentaje(redondearCosto('0.21'))).toBe('21 %')
  })

  it('una fracción con un decimal no pierde precisión (10,5 %)', () => {
    expect(formatearPorcentaje(redondearCosto('0.105'))).toBe('10,5 %')
  })

  it('cero se muestra como "0 %"', () => {
    expect(formatearPorcentaje(redondearCosto('0'))).toBe('0 %')
  })

  it('conserva hasta cuatro decimales sin ceros de relleno', () => {
    expect(formatearPorcentaje(redondearCosto('0.123456'))).toBe('12,3456 %')
  })
})
