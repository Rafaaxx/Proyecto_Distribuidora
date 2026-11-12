import { describe, expect, it } from 'vitest'

import { etiquetaIvaDescontado, ivaDescontado } from '../../../../src/domain/proveedores/ivaDescontado'

describe('ivaDescontado (11b, CST-06, TR-06: la regla congelada, no la condición actual)', () => {
  it.each([
    [{ computa_credito_fiscal: true, incluye_iva: true }, true],
    [{ computa_credito_fiscal: true, incluye_iva: false }, false],
    [{ computa_credito_fiscal: false, incluye_iva: false }, false],
    // Un registro sin crédito fiscal nunca descontó IVA aunque la columna dijera otra cosa.
    [{ computa_credito_fiscal: false, incluye_iva: true }, false],
  ])('%j -> %s', (registro, esperado) => {
    expect(ivaDescontado(registro)).toBe(esperado)
  })

  it('la etiqueta dice "IVA descontado: Sí" o "IVA descontado: No"', () => {
    expect(etiquetaIvaDescontado({ computa_credito_fiscal: true, incluye_iva: true })).toBe('IVA descontado: Sí')
    expect(etiquetaIvaDescontado({ computa_credito_fiscal: false, incluye_iva: false })).toBe('IVA descontado: No')
  })
})
