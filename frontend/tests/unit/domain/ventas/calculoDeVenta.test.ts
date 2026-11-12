import { describe, expect, it } from 'vitest'

import {
  avisoDeSaldoAFavorTrasVenta,
  calcularBrutoDelPedido,
  calcularSaldoResultanteDeVenta,
  decidirConfirmacionDeVenta,
  evaluarContadoDeConsumidorFinal,
  sumarCobranzaDeVenta,
  textoDeSaldoResultanteDeVenta,
  totalDelPedido,
} from '../../../../src/domain/ventas/calculoDeVenta'

/** VTA-02, PRC-22: la pantalla calcula igual que el servidor, con decimal.js. */
describe('totales de la venta (PRC-22, VTA-04)', () => {
  it('2 cajas + 3 unidades de Vino A a $12.500 por 6: brutos 25000.00 y 6250.00, total 31250.00', () => {
    const caja = calcularBrutoDelPedido('12500.00', 6, 12)
    const botellas = calcularBrutoDelPedido('12500.00', 6, 3)
    expect(caja.toFixed(2)).toBe('25000.00')
    expect(botellas.toFixed(2)).toBe('6250.00')
    expect(totalDelPedido([caja, botellas]).toFixed(2)).toBe('31250.00')
  })

  it('el bruto de 3 unidades sobre una referencia de 3 a $4.300 es $4.300,00 (un solo redondeo)', () => {
    expect(calcularBrutoDelPedido('4300.00', 3, 3).toFixed(2)).toBe('4300.00')
    expect(calcularBrutoDelPedido('1433.33', 1, 3).toFixed(2)).toBe('4299.99')
  })

  it('sin líneas el total es cero', () => {
    expect(totalDelPedido([]).toFixed(2)).toBe('0.00')
  })
})

describe('cobranza en el acto y saldo resultante (VTA-11, CC-04)', () => {
  it('suma de medios en vivo: un medio vacío o inválido cuenta cero', () => {
    expect(
      sumarCobranzaDeVenta([
        { medioPagoId: 'm1', importe: '15000.50', referencia: '' },
        { medioPagoId: 'm2', importe: '4999.50', referencia: '' },
        { medioPagoId: 'm3', importe: '', referencia: '' },
      ]).toFixed(2),
    ).toBe('20000.00')
  })

  it('saldo 150000 + venta 31250 - cobranza 20000 = 161250 (queda debiendo)', () => {
    expect(calcularSaldoResultanteDeVenta('150000.00', '31250.00', '20000.00').toFixed(2)).toBe('161250.00')
    expect(textoDeSaldoResultanteDeVenta('150000.00', '31250.00', '20000.00')).toBe('Queda debiendo $ 161.250,00')
  })

  it('cobrar más que el total con saldo cero deja saldo a favor y pide confirmación explícita', () => {
    expect(textoDeSaldoResultanteDeVenta('0.00', '1000.00', '1500.00')).toBe('Saldo a favor $ 500,00')
    expect(avisoDeSaldoAFavorTrasVenta('0.00', '1000.00', '1500.00')).toBe('Le queda saldo a favor de $ 500,00')
  })

  it('cobrar exacto o menos no pide confirmación', () => {
    expect(avisoDeSaldoAFavorTrasVenta('0.00', '1000.00', '1000.00')).toBeNull()
    expect(avisoDeSaldoAFavorTrasVenta('0.00', '1000.00', '0.00')).toBeNull()
    expect(textoDeSaldoResultanteDeVenta('0.00', '1000.00', '1000.00')).toBe('Saldo $ 0,00')
  })

  it('un saldo previo a favor se aplica a la venta antes de avisar', () => {
    expect(avisoDeSaldoAFavorTrasVenta('-300.00', '1000.00', '0.00')).toBeNull()
    expect(avisoDeSaldoAFavorTrasVenta('-300.00', '100.00', '0.00')).toBe('Le queda saldo a favor de $ 200,00')
  })
})

describe('qué confirmación pide la venta antes de enviar (VTA-11)', () => {
  it('con el saldo leído: pide confirmar solo si queda a favor', () => {
    expect(decidirConfirmacionDeVenta({ estado: 'leido', saldo: '0.00' }, '1000.00', '1500.00')).toEqual({
      tipo: 'saldo-a-favor',
      mensaje: 'Le queda saldo a favor de $ 500,00',
    })
    expect(decidirConfirmacionDeVenta({ estado: 'leido', saldo: '0.00' }, '1000.00', '1000.00')).toEqual({ tipo: 'ninguna' })
  })

  it('mientras el saldo carga espera; si no se pudo leer, pide confirmar solo cuando se cobra más que el total', () => {
    expect(decidirConfirmacionDeVenta({ estado: 'cargando' }, '1000.00', '0.00')).toEqual({ tipo: 'esperar' })
    expect(decidirConfirmacionDeVenta({ estado: 'error' }, '1000.00', '1500.00').tipo).toBe('saldo-ilegible')
    expect(decidirConfirmacionDeVenta({ estado: 'error' }, '1000.00', '1000.00')).toEqual({ tipo: 'ninguna' })
  })
})

/** CLI-03, D5: el consumidor final se vende solo de contado; la pantalla lo espeja antes del servidor. */
describe('consumidor final de contado (CLI-03, D5)', () => {
  it('con consumidor final y cobranza igual al total cumple', () => {
    expect(evaluarContadoDeConsumidorFinal(true, '4300.00', '4300.00')).toEqual({ aplica: true, cumple: true })
  })

  it.each([
    ['menos que el total', '4000.00'],
    ['más que el total', '4300.01'],
    ['sin cobranza', '0.00'],
  ])('con consumidor final y %s no cumple', (_caso, cobrado) => {
    expect(evaluarContadoDeConsumidorFinal(true, '4300.00', cobrado)).toEqual({ aplica: true, cumple: false })
  })

  it('con otro cliente no aplica, aunque no se cobre nada', () => {
    expect(evaluarContadoDeConsumidorFinal(false, '4300.00', '0.00')).toEqual({ aplica: false, cumple: true })
  })
})
