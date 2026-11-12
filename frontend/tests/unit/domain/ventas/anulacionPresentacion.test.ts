import { describe, expect, it } from 'vitest'

import {
  AMBITO_DE_ANULACION_DE_VENTA,
  devuelveDineroAEnviar,
  puedeAnularVenta,
  textoDeErrorDeAnulacion,
  textosDelEfectoEnCuenta,
} from '../../../../src/domain/ventas/anulacion'

/**
 * Presentación de la anulación de venta (change 19, tarea 9.1; `design.md` D2, D3, D16).
 * Reglas: VTA-20, VTA-21, VTA-22, CLI-03.
 */

describe('puedeAnularVenta (VTA-20)', () => {
  it('solo una venta CONFIRMADA y con el permiso ANULAR_VENTA', () => {
    expect(puedeAnularVenta('CONFIRMADA', true)).toBe(true)
    expect(puedeAnularVenta('ANULADA', true)).toBe(false)
    expect(puedeAnularVenta('CONFIRMADA', false)).toBe(false)
  })
})

describe('devuelveDineroAEnviar (VTA-22, CLI-03, D2, D3)', () => {
  it('sin cobranza confirmada no se envía (el servidor lo prohíbe)', () => {
    expect(devuelveDineroAEnviar({ tieneCobranza: false, esConsumidorFinal: false, eleccion: true })).toBeNull()
    expect(devuelveDineroAEnviar({ tieneCobranza: false, esConsumidorFinal: true, eleccion: null })).toBeNull()
  })

  it('con cobranza se envía la elección del usuario, y sin elegir todavía es nulo', () => {
    expect(devuelveDineroAEnviar({ tieneCobranza: true, esConsumidorFinal: false, eleccion: true })).toBe(true)
    expect(devuelveDineroAEnviar({ tieneCobranza: true, esConsumidorFinal: false, eleccion: false })).toBe(false)
    expect(devuelveDineroAEnviar({ tieneCobranza: true, esConsumidorFinal: false, eleccion: null })).toBeNull()
  })

  it('el consumidor final con cobranza devuelve siempre, elija lo que elija', () => {
    expect(devuelveDineroAEnviar({ tieneCobranza: true, esConsumidorFinal: true, eleccion: null })).toBe(true)
    expect(devuelveDineroAEnviar({ tieneCobranza: true, esConsumidorFinal: true, eleccion: false })).toBe(true)
  })
})

describe('textosDelEfectoEnCuenta (VTA-22, D4, D16)', () => {
  it('sin cobro: la cuenta baja el total de la venta', () => {
    expect(textosDelEfectoEnCuenta('150000.00', null, null)).toEqual(['La cuenta del cliente baja $ 150.000,00.'])
  })

  it('con cobro devuelto: baja el total y sube el cobro devuelto', () => {
    expect(textosDelEfectoEnCuenta('150000.00', '20000.00', true)).toEqual([
      'La cuenta del cliente baja $ 150.000,00.',
      'Y sube $ 20.000,00 por el cobro devuelto.',
    ])
  })

  it('con cobro que queda a favor: baja el total y el cobro queda a favor del cliente', () => {
    expect(textosDelEfectoEnCuenta('150000.00', '20000.00', false)).toEqual([
      'La cuenta del cliente baja $ 150.000,00.',
      'El cobro de $ 20.000,00 queda a favor del cliente.',
    ])
  })

  it('con cobro y sin elegir todavía no hay efecto que mostrar', () => {
    expect(textosDelEfectoEnCuenta('4300.00', '4300.00', null)).toEqual([])
  })
})

describe('textoDeErrorDeAnulacion (D16)', () => {
  it('traduce los códigos de la anulación a su texto', () => {
    expect(textoDeErrorDeAnulacion('VENTA_YA_ANULADA', 'x')).toMatch(/ya estaba anulada/i)
    expect(textoDeErrorDeAnulacion('UBICACION_TOMADA', 'x')).toMatch(/jornada/i)
    expect(textoDeErrorDeAnulacion('UBICACION_INACTIVA', 'x')).toMatch(/inactiva/i)
    expect(textoDeErrorDeAnulacion('MOTIVO_INVALIDO', 'x')).toMatch(/motivo/i)
  })

  it('un código sin texto propio usa el mensaje del servidor', () => {
    expect(textoDeErrorDeAnulacion('OBSERVACION_INVALIDA', 'La observación supera los 500 caracteres')).toBe(
      'La observación supera los 500 caracteres',
    )
  })
})

describe('ámbito de los motivos', () => {
  it('es ANULACION_VENTA (VTA-20, TR-09)', () => {
    expect(AMBITO_DE_ANULACION_DE_VENTA).toBe('ANULACION_VENTA')
  })
})
