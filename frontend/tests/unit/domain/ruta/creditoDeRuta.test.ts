/**
 * Change 22a, tarea 6.2: el objeto `credito` del contenido encolado (D9; CRE-09, CRE-10).
 * Mismo ejemplo de CRE-06: límite 200.000, saldo considerado 150.000, venta 80.000, cobro 20.000.
 */
import { describe, expect, it } from 'vitest'

import { ErrorDeCredito } from '../../../../src/domain/credito/errores'
import { armarCreditoDeRuta, type EntradaCreditoDeRuta } from '../../../../src/domain/ruta/creditoDeRuta'

const BASE: EntradaCreditoDeRuta = {
  limite: '200000.00',
  saldoConsiderado: '150000.00',
  politica: 'AUTORIZAR',
  toleranciaTipo: 'IMPORTE',
  toleranciaValor: '20000.00',
  total: '80000.00',
  cobranza: '20000.00',
  aceptaExceso: false,
  usuarioId: 'vendedor',
  permisosUsuario: [],
  autorizador: null,
}

describe('armarCreditoDeRuta', () => {
  it('TOLERANCIA_OFFLINE: límite, saldo, política, resolución y acepta_exceso, sin autorizador (CRE-09)', () => {
    expect(armarCreditoDeRuta(BASE)).toEqual({
      limite: '200000.00',
      saldo_considerado: '150000.00',
      politica: 'AUTORIZAR',
      resolucion: 'TOLERANCIA_OFFLINE',
      acepta_exceso: true,
    })
  })

  it('SIN_EXCESO: acepta_exceso falso (CRE-10)', () => {
    const c = armarCreditoDeRuta({ ...BASE, saldoConsiderado: '10000.00' })
    expect(c).toMatchObject({ resolucion: 'SIN_EXCESO', acepta_exceso: false, saldo_considerado: '10000.00' })
    expect(c).not.toHaveProperty('autorizador_id')
  })

  it('sin límite: límite nulo y SIN_EXCESO aunque el saldo sea enorme (CRE-01)', () => {
    expect(armarCreditoDeRuta({ ...BASE, limite: null, saldoConsiderado: '999999.00' })).toMatchObject({
      limite: null,
      resolucion: 'SIN_EXCESO',
    })
  })

  it('ADVERTENCIA_ACEPTADA con exceso aceptado (CRE-04)', () => {
    expect(armarCreditoDeRuta({ ...BASE, politica: 'ADVERTIR', aceptaExceso: true })).toMatchObject({
      resolucion: 'ADVERTENCIA_ACEPTADA',
      acepta_exceso: true,
    })
  })

  it('PERMISO_PROPIO lleva al propio usuario como autorizador (CRE-05)', () => {
    const c = armarCreditoDeRuta({ ...BASE, toleranciaValor: '5000.00', permisosUsuario: ['SUPERAR_CREDITO'] })
    expect(c).toMatchObject({ resolucion: 'PERMISO_PROPIO', autorizador_id: 'vendedor', acepta_exceso: true })
  })

  it('PIN_SUPERVISOR lleva al supervisor ya verificado como autorizador (CRE-05)', () => {
    const c = armarCreditoDeRuta({
      ...BASE,
      toleranciaValor: '5000.00',
      autorizador: { usuarioId: 'sup01', permisos: ['SUPERAR_CREDITO'] },
    })
    expect(c).toMatchObject({ resolucion: 'PIN_SUPERVISOR', autorizador_id: 'sup01' })
  })

  it('BLOQUEAR y fuera de tolerancia sin autorización no producen contenido (CRE-07)', () => {
    expect(() => armarCreditoDeRuta({ ...BASE, politica: 'BLOQUEAR' })).toThrow(ErrorDeCredito)
    expect(() => armarCreditoDeRuta({ ...BASE, toleranciaValor: '5000.00' })).toThrow(ErrorDeCredito)
  })
})
