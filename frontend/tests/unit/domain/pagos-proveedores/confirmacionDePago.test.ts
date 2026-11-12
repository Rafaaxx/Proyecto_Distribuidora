import { describe, expect, it } from 'vitest'

import {
  AVISO_SALDO_ILEGIBLE,
  decidirConfirmacionDePago,
} from '../../../../src/domain/pagos-proveedores/confirmacionDePago'

describe('decidirConfirmacionDePago (PAG-02, D3)', () => {
  it('saldo leído que queda a favor: pide la confirmación de saldo a favor con su monto', () => {
    expect(decidirConfirmacionDePago({ estado: 'leido', saldo: '153720.00' }, '160000')).toEqual({
      tipo: 'saldo-a-favor',
      mensaje: 'Queda saldo a nuestro favor de $ 6.280,00',
    })
    expect(decidirConfirmacionDePago({ estado: 'leido', saldo: '-1000.00' }, '500')).toEqual({
      tipo: 'saldo-a-favor',
      mensaje: 'Queda saldo a nuestro favor de $ 1.500,00',
    })
  })

  it('saldo leído que no queda a favor (ni siquiera en cero): no pide confirmación', () => {
    expect(decidirConfirmacionDePago({ estado: 'leido', saldo: '153720.00' }, '100000')).toEqual({ tipo: 'ninguna' })
    expect(decidirConfirmacionDePago({ estado: 'leido', saldo: '153720.00' }, '153720')).toEqual({ tipo: 'ninguna' })
  })

  it('saldo ilegible: pide confirmar sin saber si supera la deuda, sea cual sea el importe', () => {
    for (const importe of ['1', '160000']) {
      expect(decidirConfirmacionDePago({ estado: 'error' }, importe)).toEqual({
        tipo: 'saldo-ilegible',
        mensaje: AVISO_SALDO_ILEGIBLE,
      })
    }
    expect(AVISO_SALDO_ILEGIBLE).toMatch(/no pudimos leer el saldo/i)
  })

  it('saldo cargando: no se puede decidir, hay que esperar', () => {
    expect(decidirConfirmacionDePago({ estado: 'cargando' }, '100000')).toEqual({ tipo: 'esperar' })
  })
})
