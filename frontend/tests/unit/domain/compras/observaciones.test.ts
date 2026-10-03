import { describe, expect, it } from 'vitest'

import { avisoDeObservacion } from '../../../../src/domain/compras/observaciones'

describe('avisoDeObservacion (SYN-04, CMP-06, CMP-07)', () => {
  it('traduce los códigos conocidos', () => {
    expect(avisoDeObservacion('ANULACION_COMPRA_SIN_RECALCULO')).toMatch(/costo promedio no se recalcul/i)
    expect(avisoDeObservacion('STOCK_NEGATIVO')).toMatch(/stock negativo/i)
  })

  it('un código desconocido se muestra tal cual, sin perderlo', () => {
    expect(avisoDeObservacion('CODIGO_NUEVO')).toContain('CODIGO_NUEVO')
  })
})
