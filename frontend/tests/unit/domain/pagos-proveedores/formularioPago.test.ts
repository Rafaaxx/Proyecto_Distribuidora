import { describe, expect, it } from 'vitest'

import {
  avisoDeSaldoAFavorTrasPago,
  calcularFaltanteDeMedios,
  calcularSaldoResultante,
  construirSolicitudDePago,
  crearEsquemaDePago,
  etiquetaDeDiferencia,
  puedeRegistrarPago,
  saldoAFavorTrasPago,
  sumarMedios,
  textoDeSaldoResultante,
  type FormularioDePago,
} from '../../../../src/domain/pagos-proveedores/formularioPago'

const PROVEEDOR = '11111111-1111-4111-8111-111111111111'
const EFECTIVO = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const TRANSFERENCIA = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
const HOY = '2026-10-05'
const REQUIEREN_REFERENCIA: ReadonlySet<string> = new Set([TRANSFERENCIA])

function formulario(cambios: Partial<FormularioDePago> = {}): FormularioDePago {
  return {
    proveedorId: PROVEEDOR,
    fecha: HOY,
    importe: '100000',
    observacion: '',
    medios: [{ medioPagoId: EFECTIVO, importe: '100000', referencia: '' }],
    ...cambios,
  }
}

const contexto = { hoy: HOY, mediosQueRequierenReferencia: REQUIEREN_REFERENCIA }

describe('sumarMedios y faltante (INV-08, PAG-01)', () => {
  it('suma los importes de los medios con decimal.js, sin errores de coma flotante', () => {
    const suma = sumarMedios([
      { medioPagoId: EFECTIVO, importe: '0.1', referencia: '' },
      { medioPagoId: EFECTIVO, importe: '0.2', referencia: '' },
    ])

    expect(suma.toFixed(2)).toBe('0.30')
  })

  it('un importe vacío o inválido cuenta como cero', () => {
    const suma = sumarMedios([
      { medioPagoId: EFECTIVO, importe: '', referencia: '' },
      { medioPagoId: EFECTIVO, importe: 'abc', referencia: '' },
      { medioPagoId: EFECTIVO, importe: '25.50', referencia: '' },
    ])

    expect(suma.toFixed(2)).toBe('25.50')
  })

  it('faltan 52.460,00 cuando el importe es 152.460,00 y hay 100.000,00 en efectivo', () => {
    const faltante = calcularFaltanteDeMedios('152460', [{ medioPagoId: EFECTIVO, importe: '100000', referencia: '' }])

    expect(faltante.toFixed(2)).toBe('52460.00')
  })

  it('el faltante es negativo cuando los medios sobran y cero cuando suman', () => {
    const medios = [{ medioPagoId: EFECTIVO, importe: '152640', referencia: '' }]

    expect(calcularFaltanteDeMedios('152460', medios).toFixed(2)).toBe('-180.00')
    expect(calcularFaltanteDeMedios('152640', medios).isZero()).toBe(true)
  })

  it('etiqueta la diferencia: Faltan, Sobran o suman el importe', () => {
    const cien = [{ medioPagoId: EFECTIVO, importe: '100000', referencia: '' }]
    const sobra = [{ medioPagoId: EFECTIVO, importe: '152640', referencia: '' }]

    expect(etiquetaDeDiferencia(calcularFaltanteDeMedios('152460', cien))).toBe('Faltan $ 52.460,00')
    expect(etiquetaDeDiferencia(calcularFaltanteDeMedios('152460', sobra))).toBe('Sobran $ 180,00')
    expect(etiquetaDeDiferencia(calcularFaltanteDeMedios('100000', cien))).toBe('Los medios suman el importe.')
  })
})

describe('saldo resultante y su rótulo (PAG-02, CC-04)', () => {
  it('con deuda de 153.720,00 y un pago de 100.000: le debemos 53.720,00', () => {
    expect(calcularSaldoResultante('153720.00', '100000').toFixed(2)).toBe('53720.00')
    expect(textoDeSaldoResultante('153720.00', '100000')).toBe('Le debemos $ 53.720,00')
  })

  it('un pago mayor que la deuda deja saldo a nuestro favor: 160.000 contra 153.720,00 -> 6.280,00', () => {
    expect(calcularSaldoResultante('153720.00', '160000').toFixed(2)).toBe('-6280.00')
    expect(textoDeSaldoResultante('153720.00', '160000')).toBe('Saldo a nuestro favor $ 6.280,00')
  })

  it('pagar exactamente la deuda deja el saldo en cero', () => {
    expect(textoDeSaldoResultante('153720.00', '153720')).toBe('Saldo $ 0,00')
  })

  it('un importe vacío o inválido no cambia el saldo', () => {
    expect(calcularSaldoResultante('153720.00', '').toFixed(2)).toBe('153720.00')
    expect(calcularSaldoResultante('153720.00', 'x').toFixed(2)).toBe('153720.00')
  })

  it('saldoAFavorTrasPago devuelve el monto a favor solo si el saldo queda negativo', () => {
    expect(saldoAFavorTrasPago('153720.00', '160000')?.toFixed(2)).toBe('6280.00')
    expect(saldoAFavorTrasPago('153720.00', '153720')).toBeNull()
    expect(saldoAFavorTrasPago('153720.00', '100000')).toBeNull()
  })

  it('el aviso de confirmación nombra el monto a favor con la moneda', () => {
    expect(avisoDeSaldoAFavorTrasPago('153720.00', '160000')).toBe('Queda saldo a nuestro favor de $ 6.280,00')
    expect(avisoDeSaldoAFavorTrasPago('153720.00', '100000')).toBeNull()
  })

  it('un proveedor que ya tenía saldo a favor y recibe otro pago sigue a favor por el total', () => {
    expect(textoDeSaldoResultante('-1000.00', '500')).toBe('Saldo a nuestro favor $ 1.500,00')
  })
})

describe('esquema Zod del formulario de pago (PAG-01, D4, D6)', () => {
  const esquema = crearEsquemaDePago(contexto)

  function mensajes(f: FormularioDePago): string[] {
    const resultado = esquema.safeParse(f)
    return resultado.success ? [] : resultado.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`)
  }

  it('acepta un pago completo', () => {
    expect(esquema.safeParse(formulario()).success).toBe(true)
  })

  it('rechaza un importe cero, negativo, con más de dos decimales, no numérico o vacío', () => {
    for (const importe of ['0', '-5', '10.123', 'abc', '']) {
      expect(mensajes(formulario({ importe })).some((m) => m.startsWith('importe'))).toBe(true)
    }
  })

  it('acepta importes con uno o dos decimales', () => {
    const f = formulario({ importe: '100000.5', medios: [{ medioPagoId: EFECTIVO, importe: '100000.50', referencia: '' }] })

    expect(esquema.safeParse(f).success).toBe(true)
  })

  it('rechaza una fecha posterior a hoy y acepta hoy y días pasados', () => {
    expect(mensajes(formulario({ fecha: '2026-10-06' })).some((m) => m.startsWith('fecha'))).toBe(true)
    expect(esquema.safeParse(formulario({ fecha: '2026-10-05' })).success).toBe(true)
    expect(esquema.safeParse(formulario({ fecha: '2020-01-01' })).success).toBe(true)
  })

  it('rechaza una fecha vacía', () => {
    expect(mensajes(formulario({ fecha: '' })).some((m) => m.startsWith('fecha'))).toBe(true)
  })

  it('exige la referencia en el medio que la requiere, y solo en ese', () => {
    const sinReferencia = formulario({
      importe: '150',
      medios: [
        { medioPagoId: EFECTIVO, importe: '100', referencia: '' },
        { medioPagoId: TRANSFERENCIA, importe: '50', referencia: '  ' },
      ],
    })
    const conReferencia = formulario({
      importe: '150',
      medios: [
        { medioPagoId: EFECTIVO, importe: '100', referencia: '' },
        { medioPagoId: TRANSFERENCIA, importe: '50', referencia: '0042' },
      ],
    })

    expect(mensajes(sinReferencia)).toEqual([expect.stringMatching(/^medios\.1\.referencia:/)])
    expect(esquema.safeParse(conReferencia).success).toBe(true)
  })

  it('exige entre 1 y 20 medios', () => {
    const veintiuno = Array.from({ length: 21 }, () => ({ medioPagoId: EFECTIVO, importe: '1', referencia: '' }))
    const veinte = Array.from({ length: 20 }, () => ({ medioPagoId: EFECTIVO, importe: '1', referencia: '' }))

    expect(mensajes(formulario({ medios: [] })).some((m) => m.startsWith('medios'))).toBe(true)
    expect(mensajes(formulario({ importe: '21', medios: veintiuno })).some((m) => m.startsWith('medios'))).toBe(true)
    expect(esquema.safeParse(formulario({ importe: '20', medios: veinte })).success).toBe(true)
  })

  it('exige proveedor, y medio de pago elegido con importe positivo en cada medio', () => {
    const sinMedio = formulario({ medios: [{ medioPagoId: '', importe: '100000', referencia: '' }] })
    const importeCero = formulario({ medios: [{ medioPagoId: EFECTIVO, importe: '0', referencia: '' }] })

    expect(mensajes(formulario({ proveedorId: '' })).some((m) => m.startsWith('proveedorId'))).toBe(true)
    expect(mensajes(sinMedio).some((m) => m.startsWith('medios.0.medioPagoId'))).toBe(true)
    expect(mensajes(importeCero).some((m) => m.startsWith('medios.0.importe'))).toBe(true)
  })

  it('limita la observación a 500 caracteres', () => {
    expect(mensajes(formulario({ observacion: 'a'.repeat(501) })).some((m) => m.startsWith('observacion'))).toBe(true)
    expect(esquema.safeParse(formulario({ observacion: 'a'.repeat(500) })).success).toBe(true)
  })
})

describe('puedeRegistrarPago', () => {
  it('es verdadero cuando el esquema pasa y los medios suman el importe', () => {
    expect(puedeRegistrarPago(formulario(), contexto)).toBe(true)
  })

  it('es falso con faltante, con sobrante y con referencia faltante', () => {
    const faltante = formulario({ importe: '152460' })
    const sobrante = formulario({ importe: '90000' })
    const sinReferencia = formulario({ medios: [{ medioPagoId: TRANSFERENCIA, importe: '100000', referencia: '' }] })

    expect(puedeRegistrarPago(faltante, contexto)).toBe(false)
    expect(puedeRegistrarPago(sobrante, contexto)).toBe(false)
    expect(puedeRegistrarPago(sinReferencia, contexto)).toBe(false)
  })
})

describe('construirSolicitudDePago', () => {
  it('arma el cuerpo con importes de dos decimales como string, referencia nula si está vacía y observación recortada', () => {
    const cuerpo = construirSolicitudDePago(
      formulario({
        importe: '152460',
        observacion: '  paga facturas 0001-123  ',
        medios: [
          { medioPagoId: EFECTIVO, importe: '100000', referencia: '' },
          { medioPagoId: TRANSFERENCIA, importe: '52460.5', referencia: ' 0042 ' },
        ],
      }),
    )

    expect(cuerpo).toEqual({
      proveedor_id: PROVEEDOR,
      fecha: HOY,
      importe: '152460.00',
      observacion: 'paga facturas 0001-123',
      medios: [
        { medio_pago_id: EFECTIVO, importe: '100000.00', referencia: null },
        { medio_pago_id: TRANSFERENCIA, importe: '52460.50', referencia: '0042' },
      ],
    })
  })

  it('una observación vacía viaja como null', () => {
    expect(construirSolicitudDePago(formulario({ observacion: '   ' })).observacion).toBeNull()
  })
})
