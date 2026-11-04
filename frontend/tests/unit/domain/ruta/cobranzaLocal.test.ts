/**
 * Change 23, tarea 4.1 (`design.md` D3, D4; spec `ruta/area-de-ruta`, «Se cobra a un cliente desde
 * el teléfono»; cita COB-01, COB-02, INV-08, INV-03, CLI-03, CC-04): reglas locales de la cobranza.
 * Función pura: valida el formulario y calcula el saldo actual, el resultante y si queda a favor.
 */
import { describe, expect, it } from 'vitest'

import {
  OBSERVACION_MAXIMA,
  evaluarCobranzaLocal,
  type EntradaDeCobranzaLocal,
  type ErrorDeCobranzaLocal,
} from '../../../../src/domain/ruta/cobranzaLocal'

const EFECTIVO = 'medio-efectivo'
const TRANSFERENCIA = 'medio-transferencia'

const MEDIOS = [
  { id: EFECTIVO, nombre: 'Efectivo', requiere_referencia: false },
  { id: TRANSFERENCIA, nombre: 'Transferencia', requiere_referencia: true },
]

function entrada(parcial: Partial<EntradaDeCobranzaLocal> = {}): EntradaDeCobranzaLocal {
  return {
    cliente: { id: 'c1', nombre: 'Kiosco La Esquina', es_consumidor_final: false },
    saldoActual: '150000.00',
    importe: '50000',
    observacion: '',
    medios: [{ medioPagoId: EFECTIVO, importe: '50000', referencia: '' }],
    mediosPago: MEDIOS,
    ...parcial,
  }
}

const errores = (e: Partial<EntradaDeCobranzaLocal>): ErrorDeCobranzaLocal[] =>
  evaluarCobranzaLocal(entrada(e)).errores

describe('una cobranza válida (COB-01, COB-02)', () => {
  it('con un medio: válida, saldo $150.000 a $100.000 y no queda a favor', () => {
    const r = evaluarCobranzaLocal(entrada())

    expect(r.valida).toBe(true)
    expect(r.errores).toEqual([])
    expect(r.saldoActual).toBe('150000.00')
    expect(r.saldoResultante).toBe('100000.00')
    expect(r.quedaAFavor).toBe(false)
    expect(r.importeAFavor).toBeNull()
    expect(r.importe).toBe('50000.00')
  })

  it('con dos medios y referencia: $30.000 en efectivo y $20.000 por transferencia n.º 0042', () => {
    const r = evaluarCobranzaLocal(
      entrada({
        medios: [
          { medioPagoId: EFECTIVO, importe: '30000', referencia: '' },
          { medioPagoId: TRANSFERENCIA, importe: '20000.00', referencia: ' 0042 ' },
        ],
      }),
    )

    expect(r.valida).toBe(true)
    expect(r.medios).toEqual([
      { medio_pago_id: EFECTIVO, importe: '30000.00', referencia: null },
      { medio_pago_id: TRANSFERENCIA, importe: '20000.00', referencia: '0042' },
    ])
  })

  it('el mismo medio puede repetirse y 20 medios son el máximo', () => {
    const veinte = Array.from({ length: 20 }, () => ({ medioPagoId: EFECTIVO, importe: '2500', referencia: '' }))

    expect(errores({ medios: veinte, importe: '50000' })).toEqual([])
    expect(
      errores({ medios: [...veinte, { medioPagoId: EFECTIVO, importe: '0.01', referencia: '' }], importe: '50000.01' }),
    ).toContain('MEDIOS_DEMASIADOS')
  })
})

describe('el importe (COB-01, INV-03)', () => {
  it.each([
    ['0', 'cero'],
    ['-100', 'negativo'],
    ['', 'vacío'],
    ['abc', 'no numérico'],
    ['100.123', 'tres decimales'],
  ])('%s (%s) es inválido', (importe) => {
    expect(errores({ importe, medios: [{ medioPagoId: EFECTIVO, importe: '100', referencia: '' }] })).toContain(
      'IMPORTE_INVALIDO',
    )
  })

  it('con un decimal es válido y se normaliza a dos decimales', () => {
    const r = evaluarCobranzaLocal(
      entrada({ importe: '12500.5', medios: [{ medioPagoId: EFECTIVO, importe: '12500.50', referencia: '' }] }),
    )

    expect(r.errores).toEqual([])
    expect(r.importe).toBe('12500.50')
  })

  it('conserva la exactitud: 0.10 más 0.20 suman 0.30', () => {
    const r = evaluarCobranzaLocal(
      entrada({
        importe: '0.30',
        medios: [
          { medioPagoId: EFECTIVO, importe: '0.10', referencia: '' },
          { medioPagoId: EFECTIVO, importe: '0.20', referencia: '' },
        ],
      }),
    )

    expect(r.errores).toEqual([])
  })
})

describe('los medios (COB-02, INV-08)', () => {
  it('sin medios es inválida', () => {
    expect(errores({ medios: [] })).toContain('SIN_MEDIOS')
  })

  it('que no suman el importe: faltan $1.000 (INV-08)', () => {
    const r = evaluarCobranzaLocal(entrada({ medios: [{ medioPagoId: EFECTIVO, importe: '49000', referencia: '' }] }))

    expect(r.valida).toBe(false)
    expect(r.errores).toContain('MEDIOS_NO_SUMAN')
    expect(r.faltante).toBe('1000.00')
  })

  it('que suman de más: sobran $1.000', () => {
    const r = evaluarCobranzaLocal(entrada({ medios: [{ medioPagoId: EFECTIVO, importe: '51000', referencia: '' }] }))

    expect(r.errores).toContain('MEDIOS_NO_SUMAN')
    expect(r.faltante).toBe('-1000.00')
  })

  it('con un medio sin elegir o de importe no positivo es inválida', () => {
    expect(errores({ medios: [{ medioPagoId: '', importe: '50000', referencia: '' }] })).toContain('MEDIO_INVALIDO')
    expect(errores({ medios: [{ medioPagoId: EFECTIVO, importe: '0', referencia: '' }] })).toContain('MEDIO_INVALIDO')
  })

  it('con un medio que no está entre los activos del bootstrap es inválida', () => {
    expect(
      errores({ medios: [{ medioPagoId: 'medio-dado-de-baja', importe: '50000', referencia: '' }] }),
    ).toContain('MEDIO_INVALIDO')
  })

  it('la referencia es obligatoria donde el medio la exige: vacía o de solo espacios no vale', () => {
    const con = (referencia: string) =>
      errores({
        importe: '20000',
        medios: [{ medioPagoId: TRANSFERENCIA, importe: '20000', referencia }],
      })

    expect(con('')).toContain('REFERENCIA_FALTANTE')
    expect(con('   ')).toContain('REFERENCIA_FALTANTE')
    expect(con('0042')).toEqual([])
  })
})

describe('el cliente (CLI-03, COB-01)', () => {
  it('sin cliente elegido es inválida', () => {
    expect(errores({ cliente: null })).toContain('SIN_CLIENTE')
  })

  it('al consumidor final no se le cobra: CONSUMIDOR_FINAL_SIN_CUENTA', () => {
    const e = errores({ cliente: { id: 'cf', nombre: 'Consumidor final', es_consumidor_final: true } })

    expect(e).toContain('CONSUMIDOR_FINAL')
  })
})

describe('la observación (COB-01)', () => {
  it('se recorta y vacía queda null', () => {
    expect(evaluarCobranzaLocal(entrada({ observacion: '  Pago de octubre  ' })).observacion).toBe('Pago de octubre')
    expect(evaluarCobranzaLocal(entrada({ observacion: '   ' })).observacion).toBeNull()
  })

  it(`admite hasta ${OBSERVACION_MAXIMA} caracteres y rechaza uno más`, () => {
    expect(errores({ observacion: 'a'.repeat(OBSERVACION_MAXIMA) })).toEqual([])
    expect(errores({ observacion: 'a'.repeat(OBSERVACION_MAXIMA + 1) })).toContain('OBSERVACION_LARGA')
  })

  it('los espacios de los bordes no cuentan para el máximo', () => {
    expect(errores({ observacion: ` ${'a'.repeat(OBSERVACION_MAXIMA)} ` })).toEqual([])
  })
})

describe('el saldo después del cobro (CC-04, COB-01)', () => {
  it('cobrar $160.000 a quien debe $150.000 deja $10.000 a favor (saldo -10.000)', () => {
    const r = evaluarCobranzaLocal(
      entrada({ importe: '160000', medios: [{ medioPagoId: EFECTIVO, importe: '160000', referencia: '' }] }),
    )

    expect(r.valida).toBe(true)
    expect(r.saldoResultante).toBe('-10000.00')
    expect(r.quedaAFavor).toBe(true)
    expect(r.importeAFavor).toBe('10000.00')
  })

  it('cobrar justo la deuda deja saldo cero, que no es a favor', () => {
    const r = evaluarCobranzaLocal(
      entrada({ importe: '150000', medios: [{ medioPagoId: EFECTIVO, importe: '150000', referencia: '' }] }),
    )

    expect(r.saldoResultante).toBe('0.00')
    expect(r.quedaAFavor).toBe(false)
  })

  it('con el importe todavía inválido el saldo resultante es el actual', () => {
    const r = evaluarCobranzaLocal(entrada({ importe: '' }))

    expect(r.saldoActual).toBe('150000.00')
    expect(r.saldoResultante).toBe('150000.00')
    expect(r.quedaAFavor).toBe(false)
  })

  it('sin cliente no hay saldo actual ni resultante', () => {
    const r = evaluarCobranzaLocal(entrada({ cliente: null, saldoActual: null }))

    expect(r.saldoActual).toBeNull()
    expect(r.saldoResultante).toBeNull()
  })
})
