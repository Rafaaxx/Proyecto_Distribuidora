import { describe, expect, it } from 'vitest'

import { formatearCostoDeApi } from '../../../../src/domain/stock/costos'

/** Los costos llegan como string de la API y se formatean con `lib/money.ts`,
 * sin pasar nunca por `number` (INV-03). */
describe('formatearCostoDeApi', () => {
  it('formatea un costo con seis decimales y miles en es-AR', () => {
    expect(formatearCostoDeApi('1050.000000')).toBe('$ 1.050,000000')
    expect(formatearCostoDeApi('1133.333333')).toBe('$ 1.133,333333')
    expect(formatearCostoDeApi('0.833333')).toBe('$ 0,833333')
  })

  it('un costo nulo es "Sin costo" (D10: no es cero)', () => {
    expect(formatearCostoDeApi(null)).toBe('Sin costo')
    expect(formatearCostoDeApi(undefined)).toBe('Sin costo')
  })
})
