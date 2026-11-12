import { describe, expect, it } from 'vitest'

import {
  CONDICIONES_IVA,
  computaCreditoFiscalDe,
  costosParaRevisar,
  etiquetaDeCondicionIva,
} from '../../../../src/domain/configuracion/condicionIva'

describe('computaCreditoFiscalDe (CST-06)', () => {
  it.each([
    ['RESPONSABLE_INSCRIPTO', true],
    ['MONOTRIBUTO', false],
    ['EXENTO', false],
  ] as const)('%s -> %s', (condicion, esperado) => {
    expect(computaCreditoFiscalDe(condicion)).toBe(esperado)
  })
})

describe('costosParaRevisar (11b, D10)', () => {
  const resumen = { fecha: '2026-10-03', con_credito_fiscal: 3, sin_credito_fiscal: 12 }

  it('pasar a inscripto: hay que revisar los costos calculados sin descontar IVA', () => {
    expect(costosParaRevisar('RESPONSABLE_INSCRIPTO', resumen)).toBe(12)
  })

  it.each(['MONOTRIBUTO', 'EXENTO'] as const)('pasar a %s: los calculados descontando IVA', (destino) => {
    expect(costosParaRevisar(destino, resumen)).toBe(3)
  })
})

describe('etiquetas', () => {
  it('cada condición tiene su texto y el orden es el del dominio cerrado', () => {
    expect(CONDICIONES_IVA).toEqual(['RESPONSABLE_INSCRIPTO', 'MONOTRIBUTO', 'EXENTO'])
    expect(etiquetaDeCondicionIva('RESPONSABLE_INSCRIPTO')).toBe('Responsable inscripto')
    expect(etiquetaDeCondicionIva('MONOTRIBUTO')).toBe('Monotributo')
    expect(etiquetaDeCondicionIva('EXENTO')).toBe('Exento')
  })
})
