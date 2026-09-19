import { describe, expect, it } from 'vitest'

import {
  EntradaNoEsDineroExactoError,
  formatearImporte,
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
  it('formatea un importe para mostrar con dos decimales', () => {
    expect(formatearImporte(redondearImporte('31250'))).toBe('31250.00')
  })
})
