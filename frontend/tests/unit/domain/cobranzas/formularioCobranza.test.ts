import { describe, expect, it } from 'vitest'

import {
  avisoDeSaldoAFavorTrasCobranza,
  calcularSaldoResultante,
  construirSolicitudDeCobranza,
  crearEsquemaDeCobranza,
  decidirConfirmacionDeCobranza,
  etiquetaDeFaltante,
  puedeRegistrarCobranza,
  textoDeSaldoResultante,
  type FormularioDeCobranza,
} from '../../../../src/domain/cobranzas/formularioCobranza'
import { calcularFaltanteDeMedios } from '../../../../src/domain/pagos-proveedores/formularioPago'

const CLIENTE = '11111111-1111-4111-8111-111111111111'
const COBRANZA = '77777777-7777-4777-8777-777777777777'
const EFECTIVO = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const TRANSFERENCIA = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
const contexto = { mediosQueRequierenReferencia: new Set([TRANSFERENCIA]) as ReadonlySet<string> }

function formulario(cambios: Partial<FormularioDeCobranza> = {}): FormularioDeCobranza {
  return {
    clienteId: CLIENTE,
    importe: '50000',
    observacion: '',
    medios: [
      { medioPagoId: EFECTIVO, importe: '30000', referencia: '' },
      { medioPagoId: TRANSFERENCIA, importe: '20000', referencia: '0042' },
    ],
    ...cambios,
  }
}

describe('faltante y saldo resultante (COB-02, INV-08, INV-03)', () => {
  it('con los medios sumando el importe dice "Falta $ 0,00" (escenario de la spec)', () => {
    const faltante = calcularFaltanteDeMedios('50000', formulario().medios)

    expect(etiquetaDeFaltante(faltante)).toBe('Falta $ 0,00')
  })

  it.each([
    ['50000', '30000', 'Falta $ 20.000,00'],
    ['50000', '51000.50', 'Sobra $ 1.000,50'],
  ])('importe %s con medios %s: %s', (importe, medio, esperado) => {
    const faltante = calcularFaltanteDeMedios(importe, [{ medioPagoId: EFECTIVO, importe: medio, referencia: '' }])

    expect(etiquetaDeFaltante(faltante)).toBe(esperado)
  })

  it('el saldo resultante de un cliente que debe $150.000 y paga $50.000 es "Queda debiendo $ 100.000,00"', () => {
    expect(textoDeSaldoResultante('150000.00', '50000')).toBe('Queda debiendo $ 100.000,00')
  })

  it.each([
    ['150000.00', '150000', 'Saldo $ 0,00'],
    ['150000.00', '160000', 'Saldo a favor $ 10.000,00'],
    ['-2500.50', '100', 'Saldo a favor $ 2.600,50'],
    ['0.10', '0.30', 'Saldo a favor $ 0,20'],
  ])('saldo %s, importe %s: %s (sin coma flotante)', (saldo, importe, esperado) => {
    expect(textoDeSaldoResultante(saldo, importe)).toBe(esperado)
  })

  it('un importe ilegible cuenta como cero para el saldo resultante', () => {
    expect(calcularSaldoResultante('1000.00', 'abc').toFixed(2)).toBe('1000.00')
  })
})

describe('confirmación por saldo a favor (COB-03, D5)', () => {
  it('pide confirmar "Le queda saldo a favor de $ 10.000,00" si paga de más', () => {
    expect(avisoDeSaldoAFavorTrasCobranza('150000.00', '160000')).toBe('Le queda saldo a favor de $ 10.000,00')
  })

  it('no avisa si el pago deja deuda o cero', () => {
    expect(avisoDeSaldoAFavorTrasCobranza('150000.00', '50000')).toBeNull()
    expect(avisoDeSaldoAFavorTrasCobranza('150000.00', '150000')).toBeNull()
  })

  it('decide según la lectura del saldo: espera, ilegible, a favor o ninguna', () => {
    expect(decidirConfirmacionDeCobranza({ estado: 'cargando' }, '10')).toEqual({ tipo: 'esperar' })
    expect(decidirConfirmacionDeCobranza({ estado: 'error' }, '10').tipo).toBe('saldo-ilegible')
    expect(decidirConfirmacionDeCobranza({ estado: 'leido', saldo: '5.00' }, '10')).toEqual({
      tipo: 'saldo-a-favor',
      mensaje: 'Le queda saldo a favor de $ 5,00',
    })
    expect(decidirConfirmacionDeCobranza({ estado: 'leido', saldo: '500.00' }, '10')).toEqual({ tipo: 'ninguna' })
  })
})

describe('esquema y habilitación (COB-01, COB-02)', () => {
  it('un formulario completo y exacto se puede registrar', () => {
    expect(puedeRegistrarCobranza(formulario(), contexto)).toBe(true)
  })

  it('sin cliente, no', () => {
    const resultado = crearEsquemaDeCobranza(contexto).safeParse(formulario({ clienteId: '' }))

    expect(resultado.success).toBe(false)
    expect(resultado.error?.issues[0]?.message).toBe('Elegí un cliente.')
  })

  it.each(['0', '-5', '10.123', '', 'abc'])('el importe "%s" no es válido', (importe) => {
    expect(puedeRegistrarCobranza(formulario({ importe }), contexto)).toBe(false)
  })

  it('la referencia de solo espacios no alcanza en un medio que la exige', () => {
    const f = formulario({
      medios: [
        { medioPagoId: EFECTIVO, importe: '30000', referencia: '' },
        { medioPagoId: TRANSFERENCIA, importe: '20000', referencia: '   ' },
      ],
    })

    expect(puedeRegistrarCobranza(f, contexto)).toBe(false)
  })

  it('medios que no suman el importe no se pueden registrar aunque el esquema pase', () => {
    const f = formulario({ importe: '60000' })

    expect(crearEsquemaDeCobranza(contexto).safeParse(f).success).toBe(true)
    expect(puedeRegistrarCobranza(f, contexto)).toBe(false)
  })

  it('admite de 1 a 20 medios y observación de hasta 500', () => {
    const veintiuno = Array.from({ length: 21 }, () => ({ medioPagoId: EFECTIVO, importe: '1', referencia: '' }))

    expect(puedeRegistrarCobranza(formulario({ importe: '21', medios: veintiuno }), contexto)).toBe(false)
    expect(puedeRegistrarCobranza(formulario({ medios: [] }), contexto)).toBe(false)
    expect(puedeRegistrarCobranza(formulario({ observacion: 'x'.repeat(501) }), contexto)).toBe(false)
    expect(puedeRegistrarCobranza(formulario({ observacion: 'x'.repeat(500) }), contexto)).toBe(true)
  })
})

describe('cuerpo del comando (INV-03, INV-06)', () => {
  it('manda importes como string de dos decimales, referencia nula si está vacía y el id de cobranza dado', () => {
    const solicitud = construirSolicitudDeCobranza(formulario({ observacion: '  pagó en mostrador ' }), COBRANZA)

    expect(solicitud).toEqual({
      cobranza_id: COBRANZA,
      cliente_id: CLIENTE,
      importe: '50000.00',
      observacion: 'pagó en mostrador',
      medios: [
        { medio_pago_id: EFECTIVO, importe: '30000.00', referencia: null },
        { medio_pago_id: TRANSFERENCIA, importe: '20000.00', referencia: '0042' },
      ],
    })
  })

  it('una observación vacía viaja nula y un importe con decimales conserva su valor exacto', () => {
    const solicitud = construirSolicitudDeCobranza(
      formulario({ importe: '0.3', medios: [{ medioPagoId: EFECTIVO, importe: '0.30', referencia: '' }] }),
      COBRANZA,
    )

    expect(solicitud.observacion).toBeNull()
    expect(solicitud.importe).toBe('0.30')
    expect(typeof solicitud.importe).toBe('string')
  })
})
