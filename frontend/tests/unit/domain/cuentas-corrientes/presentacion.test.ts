import { describe, expect, it } from 'vitest'

import {
  columnasDeMovimiento,
  etiquetaDeTipo,
  etiquetasDeSentido,
  formatearMonto,
  textoDeSaldo,
} from '../../../../src/domain/cuentas-corrientes/presentacion'

/**
 * Change 08, tarea 7.2/7.3: rotulado del saldo según el signo y según la
 * cuenta (spec `administracion-de-cuentas-corrientes`, "La ficha muestra el
 * saldo..."). Convención (CC-04, `01` §2): el saldo positivo es lo que la otra
 * parte nos debe (cliente) o lo que le debemos (proveedor). Los importes
 * llegan como string y nunca pasan por `number`.
 */
describe('textoDeSaldo', () => {
  it('cliente con saldo positivo: "Nos debe"', () => {
    expect(textoDeSaldo('CLIENTE', '150000.00')).toBe('Nos debe $ 150.000,00')
  })

  it('cliente con saldo negativo: "Saldo a favor" con el importe sin signo', () => {
    expect(textoDeSaldo('CLIENTE', '-2500.50')).toBe('Saldo a favor $ 2.500,50')
  })

  it('proveedor con saldo positivo: "Le debemos"', () => {
    expect(textoDeSaldo('PROVEEDOR', '9000.00')).toBe('Le debemos $ 9.000,00')
  })

  it('proveedor con saldo negativo: "Saldo a nuestro favor"', () => {
    expect(textoDeSaldo('PROVEEDOR', '-3000.00')).toBe('Saldo a nuestro favor $ 3.000,00')
  })

  it.each(['CLIENTE', 'PROVEEDOR'] as const)('saldo cero de %s: "Saldo $ 0,00"', (cuenta) => {
    expect(textoDeSaldo(cuenta, '0.00')).toBe('Saldo $ 0,00')
  })

  it('no pierde precisión con importes que un número binario no representa', () => {
    expect(textoDeSaldo('CLIENTE', '9007199254740993.10')).toBe('Nos debe $ 9.007.199.254.740.993,10')
  })
})

describe('formatearMonto', () => {
  it('antepone el signo de pesos y conserva el signo negativo', () => {
    expect(formatearMonto('130000.00')).toBe('$ 130.000,00')
    expect(formatearMonto('-3000.00')).toBe('$ -3.000,00')
  })
})

describe('etiquetasDeSentido', () => {
  it('cliente: Nos debe / Saldo a favor del cliente', () => {
    expect(etiquetasDeSentido('CLIENTE')).toEqual({
      AUMENTA: 'Nos debe',
      REDUCE: 'Saldo a favor del cliente',
    })
  })

  it('proveedor: Le debemos / Saldo a favor nuestro', () => {
    expect(etiquetasDeSentido('PROVEEDOR')).toEqual({
      AUMENTA: 'Le debemos',
      REDUCE: 'Saldo a favor nuestro',
    })
  })
})

describe('columnasDeMovimiento', () => {
  it('un movimiento que aumenta llena solo la columna de aumento', () => {
    expect(columnasDeMovimiento({ sentido: 'AUMENTA', importe: '150000.00' })).toEqual({
      aumento: '$ 150.000,00',
      reduccion: null,
    })
  })

  it('un movimiento que reduce llena solo la columna de reducción', () => {
    expect(columnasDeMovimiento({ sentido: 'REDUCE', importe: '20000.00' })).toEqual({
      aumento: null,
      reduccion: '$ 20.000,00',
    })
  })
})

describe('etiquetaDeTipo', () => {
  it('traduce los tipos del catálogo y deja pasar uno desconocido', () => {
    expect(etiquetaDeTipo('SALDO_INICIAL')).toBe('Saldo inicial')
    expect(etiquetaDeTipo('COBRANZA')).toBe('Cobranza')
    expect(etiquetaDeTipo('ANULACION_PAGO')).toBe('Anulación de pago')
    expect(etiquetaDeTipo('TIPO_FUTURO')).toBe('TIPO_FUTURO')
  })
})
