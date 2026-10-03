import { describe, expect, it } from 'vitest'

import {
  calcularFaltanteDeMedios,
  calcularVistaPrevia,
  construirCostoInformar,
  construirSolicitudDeCompra,
  contextoDeLinea,
  presentacionesDeCompra,
  puedeConfirmar,
  porcentajeAFraccion,
  type ContextoDeLinea,
  type LineaDeFormulario,
} from '../../../../src/domain/compras/formularioCompra'
import { ErrorDeCompra } from '../../../../src/domain/compras/calculoCompra'

const PRODUCTO = '44444444-4444-4444-8444-444444444444'
const PRESENTACION = '55555555-5555-4555-8555-555555555555'
const PROVEEDOR = '22222222-2222-4222-8222-222222222222'
const UBICACION = '33333333-3333-4333-8333-333333333333'
const MEDIO = '66666666-6666-4666-8666-666666666666'

const CAJA_X12_CON_IVA: LineaDeFormulario = {
  productoId: PRODUCTO,
  presentacionId: PRESENTACION,
  cantidad: '1',
  valor: '18000.00',
  incluyeIva: true,
  bonificacionPorcentaje: '0',
}
const CONTEXTO_CAJA_X12: ContextoDeLinea = { unidadesPresentacion: 12, alicuota: '0.210000' }

describe('porcentajeAFraccion', () => {
  it.each([
    ['10', '0.100000'],
    ['0', '0.000000'],
    ['12.5', '0.125000'],
    ['', '0.000000'],
  ])('%j -> %s', (entrada, esperado) => {
    expect(porcentajeAFraccion(entrada)).toBe(esperado)
  })

  it.each(['abc', '100', '-1', '10.12345'])('rechaza %j con BONIFICACION_INVALIDA', (entrada) => {
    expect(() => porcentajeAFraccion(entrada)).toThrowError(ErrorDeCompra)
    try {
      porcentajeAFraccion(entrada)
    } catch (error) {
      expect((error as ErrorDeCompra).codigo).toBe('BONIFICACION_INVALIDA')
    }
  })
})

describe('calcularVistaPrevia (CMP-02, mismos casos que el servidor)', () => {
  it('Caja x12 con IVA 21%: costo base 1239.669421, neto 14876.03, total de factura sugerido 18000.00', () => {
    const vista = calcularVistaPrevia([CAJA_X12_CON_IVA], [CONTEXTO_CAJA_X12])

    const linea = vista.lineas[0]
    expect(linea?.estado).toBe('lista')
    if (linea?.estado !== 'lista') throw new Error('se esperaba una línea lista')
    expect(linea.calculada.cantidadBase).toBe(12)
    expect(linea.calculada.costoBase.toFixed(6)).toBe('1239.669421')
    expect(linea.calculada.importeNeto.toFixed(2)).toBe('14876.03')
    expect(vista.totales?.totalNeto.toFixed(2)).toBe('14876.03')
    expect(vista.totales?.totalFacturaSugerido.toFixed(2)).toBe('18000.00')
    expect(vista.totales?.ivaSugerido.toFixed(2)).toBe('3123.97')
  })

  it('con bonificación 10% sin IVA: costo base 1350.000000 y neto 16200.00', () => {
    const vista = calcularVistaPrevia(
      [{ ...CAJA_X12_CON_IVA, incluyeIva: false, bonificacionPorcentaje: '10' }],
      [CONTEXTO_CAJA_X12],
    )

    const linea = vista.lineas[0]
    if (linea?.estado !== 'lista') throw new Error('se esperaba una línea lista')
    expect(linea.calculada.costoBase.toFixed(6)).toBe('1350.000000')
    expect(linea.calculada.importeNeto.toFixed(2)).toBe('16200.00')
  })

  it('cantidad fraccionaria válida: 2.5 cajas x6 son 15 unidades base', () => {
    const vista = calcularVistaPrevia(
      [{ ...CAJA_X12_CON_IVA, cantidad: '2.5', valor: '6000.00', incluyeIva: false }],
      [{ unidadesPresentacion: 6, alicuota: '0.210000' }],
    )

    const linea = vista.lineas[0]
    if (linea?.estado !== 'lista') throw new Error('se esperaba una línea lista')
    expect(linea.calculada.cantidadBase).toBe(15)
    expect(linea.calculada.importeNeto.toFixed(2)).toBe('15000.00')
  })

  it('suma varias líneas: totales de neto y de factura sugerido', () => {
    const vista = calcularVistaPrevia(
      [CAJA_X12_CON_IVA, { ...CAJA_X12_CON_IVA, incluyeIva: false }],
      [CONTEXTO_CAJA_X12, CONTEXTO_CAJA_X12],
    )

    expect(vista.totales?.totalNeto.toFixed(2)).toBe('32876.03')
    expect(vista.totales?.totalFacturaSugerido.toFixed(2)).toBe('39780.00')
  })

  it('una línea sin datos todavía queda incompleta y no hay totales', () => {
    const vista = calcularVistaPrevia(
      [CAJA_X12_CON_IVA, { ...CAJA_X12_CON_IVA, valor: '' }],
      [CONTEXTO_CAJA_X12, CONTEXTO_CAJA_X12],
    )

    expect(vista.lineas.map((l) => l.estado)).toEqual(['lista', 'incompleta'])
    expect(vista.totales).toBeNull()
  })

  it('sin contexto de catálogo (presentación sin elegir) la línea está incompleta', () => {
    const vista = calcularVistaPrevia([CAJA_X12_CON_IVA], [{ unidadesPresentacion: null, alicuota: null }])

    expect(vista.lineas[0]?.estado).toBe('incompleta')
  })

  it('una cantidad que no da entero en unidad base es un error de línea con el código del servidor', () => {
    const vista = calcularVistaPrevia(
      [{ ...CAJA_X12_CON_IVA, cantidad: '2.3' }],
      [{ unidadesPresentacion: 6, alicuota: '0.210000' }],
    )

    const linea = vista.lineas[0]
    expect(linea).toMatchObject({ estado: 'error', codigo: 'CANTIDAD_INVALIDA' })
    expect(vista.totales).toBeNull()
  })

  it('un error en una línea no esconde el cálculo de las otras', () => {
    const vista = calcularVistaPrevia(
      [CAJA_X12_CON_IVA, { ...CAJA_X12_CON_IVA, valor: '0' }],
      [CONTEXTO_CAJA_X12, CONTEXTO_CAJA_X12],
    )

    expect(vista.lineas.map((l) => l.estado)).toEqual(['lista', 'error'])
    expect(vista.lineas[1]).toMatchObject({ codigo: 'VALOR_INVALIDO' })
  })

  it('sin líneas no hay totales', () => {
    expect(calcularVistaPrevia([], []).totales).toBeNull()
  })
})

describe('calcularFaltanteDeMedios (INV-08)', () => {
  it('faltante = total - suma de medios', () => {
    expect(
      calcularFaltanteDeMedios('18000.00', [
        { medioPagoId: MEDIO, importe: '10000.00', referencia: '' },
        { medioPagoId: MEDIO, importe: '5000.50', referencia: '' },
      ]).toFixed(2),
    ).toBe('2999.50')
  })

  it('cero cuando los medios suman el total; negativo si se pasan', () => {
    expect(calcularFaltanteDeMedios('100.00', [{ medioPagoId: MEDIO, importe: '100.00', referencia: '' }]).toFixed(2)).toBe('0.00')
    expect(calcularFaltanteDeMedios('100.00', [{ medioPagoId: MEDIO, importe: '120.00', referencia: '' }]).toFixed(2)).toBe('-20.00')
  })

  it('un importe vacío o inválido cuenta como cero, sin lanzar', () => {
    expect(
      calcularFaltanteDeMedios('100.00', [
        { medioPagoId: MEDIO, importe: '', referencia: '' },
        { medioPagoId: MEDIO, importe: 'abc', referencia: '' },
      ]).toFixed(2),
    ).toBe('100.00')
  })

  it('sin medios, falta todo el total', () => {
    expect(calcularFaltanteDeMedios('250.00', []).toFixed(2)).toBe('250.00')
  })
})

describe('construirSolicitudDeCompra', () => {
  const BASE = {
    proveedorId: PROVEEDOR,
    fecha: '2026-05-10',
    ubicacionId: UBICACION,
    numeroComprobante: ' A-0001 ',
    observacion: '',
    lineas: [CAJA_X12_CON_IVA],
    medios: [],
  }

  it('a crédito: importes como string, bonificación como fracción, sin medios', () => {
    const solicitud = construirSolicitudDeCompra({ ...BASE, condicion: 'CREDITO' }, '18000')

    expect(solicitud).toEqual({
      proveedor_id: PROVEEDOR,
      fecha: '2026-05-10',
      ubicacion_id: UBICACION,
      condicion: 'CREDITO',
      total_factura: '18000.00',
      numero_comprobante: 'A-0001',
      observacion: null,
      lineas: [
        {
          producto_id: PRODUCTO,
          presentacion_id: PRESENTACION,
          cantidad: '1',
          valor: '18000.00',
          incluye_iva: true,
          bonificacion: '0.000000',
        },
      ],
      medios: [],
    })
  })

  it('de contado: manda los medios; la referencia vacía va como null y la dada recortada', () => {
    const solicitud = construirSolicitudDeCompra(
      {
        ...BASE,
        condicion: 'CONTADO',
        numeroComprobante: '',
        observacion: ' pagó en el momento ',
        medios: [
          { medioPagoId: MEDIO, importe: '10000', referencia: '' },
          { medioPagoId: MEDIO, importe: '8000.50', referencia: ' 123 ' },
        ],
      },
      '18000.50',
    )

    expect(solicitud.condicion).toBe('CONTADO')
    expect(solicitud.total_factura).toBe('18000.50')
    expect(solicitud.numero_comprobante).toBeNull()
    expect(solicitud.observacion).toBe('pagó en el momento')
    expect(solicitud.medios).toEqual([
      { medio_pago_id: MEDIO, importe: '10000.00', referencia: null },
      { medio_pago_id: MEDIO, importe: '8000.50', referencia: '123' },
    ])
  })

  it('a crédito ignora los medios que hubiera cargado el usuario', () => {
    const solicitud = construirSolicitudDeCompra(
      { ...BASE, condicion: 'CREDITO', medios: [{ medioPagoId: MEDIO, importe: '1', referencia: '' }] },
      '18000',
    )

    expect(solicitud.medios).toEqual([])
  })
})

describe('construirCostoInformar (CMP-04, D7)', () => {
  it('toma presentación, valor, IVA y bonificación de la línea y la vigencia desde la fecha de la compra', () => {
    const costo = construirCostoInformar(
      { ...CAJA_X12_CON_IVA, bonificacionPorcentaje: '10' },
      '2026-05-10',
    )

    expect(costo).toEqual({
      producto_id: PRODUCTO,
      presentacion_id: PRESENTACION,
      valor: '18000.00',
      incluye_iva: true,
      bonificacion: '0.100000',
      vigencia_desde: '2026-05-10',
    })
  })

  it('el valor se normaliza a dos decimales', () => {
    expect(construirCostoInformar({ ...CAJA_X12_CON_IVA, valor: '1100' }, '2026-05-10').valor).toBe('1100.00')
  })
})

const PRESENTACIONES = [
  { id: 'caja', nombre: 'Caja x12', unidades_base: 12, activo: true, usar_en_compra: true },
  { id: 'solo-venta', nombre: 'Caja x6', unidades_base: 6, activo: true, usar_en_compra: false },
  { id: 'inactiva', nombre: 'Pack', unidades_base: 3, activo: false, usar_en_compra: true },
]
const ALICUOTAS = [
  { id: 'a21', valor: '0.210000' },
  { id: 'a0', valor: '0.000000' },
]

describe('presentacionesDeCompra y contextoDeLinea (catálogo -> línea)', () => {
  it('ofrece solo las presentaciones activas y de compra', () => {
    expect(presentacionesDeCompra(PRESENTACIONES).map((p) => p.id)).toEqual(['caja'])
    expect(presentacionesDeCompra(undefined)).toEqual([])
  })

  it('arma unidades y alícuota de la presentación elegida y la alícuota del producto', () => {
    expect(contextoDeLinea({ alicuota_id: 'a21', presentaciones: PRESENTACIONES }, 'caja', ALICUOTAS)).toEqual({
      unidadesPresentacion: 12,
      alicuota: '0.210000',
    })
    expect(contextoDeLinea({ alicuota_id: 'a0', presentaciones: PRESENTACIONES }, 'caja', ALICUOTAS)).toEqual({
      unidadesPresentacion: 12,
      alicuota: '0.000000',
    })
  })

  it('sin producto cargado, sin presentación elegida o con una alícuota desconocida, deja null lo que falta', () => {
    expect(contextoDeLinea(undefined, 'caja', ALICUOTAS)).toEqual({ unidadesPresentacion: null, alicuota: null })
    expect(contextoDeLinea({ alicuota_id: 'a21', presentaciones: PRESENTACIONES }, '', ALICUOTAS)).toEqual({
      unidadesPresentacion: null,
      alicuota: '0.210000',
    })
    expect(contextoDeLinea({ alicuota_id: 'x', presentaciones: PRESENTACIONES }, 'caja', ALICUOTAS)).toEqual({
      unidadesPresentacion: 12,
      alicuota: null,
    })
  })
})

describe('puedeConfirmar', () => {
  const lista = calcularVistaPrevia([CAJA_X12_CON_IVA], [CONTEXTO_CAJA_X12])
  const base = {
    formulario: {
      proveedorId: PROVEEDOR,
      fecha: '2026-05-10',
      ubicacionId: UBICACION,
      condicion: 'CREDITO' as const,
      numeroComprobante: '',
      observacion: '',
      lineas: [CAJA_X12_CON_IVA],
      medios: [],
    },
    vistaPrevia: lista,
    totalFactura: '18000.00',
    mediosRequierenReferencia: new Set<string>(),
  }

  it('a crédito con todo completo se puede confirmar', () => {
    expect(puedeConfirmar(base)).toBe(true)
  })

  it.each([
    ['sin proveedor', { formulario: { ...base.formulario, proveedorId: '' } }],
    ['sin ubicación', { formulario: { ...base.formulario, ubicacionId: '' } }],
    ['sin fecha', { formulario: { ...base.formulario, fecha: '' } }],
    ['con una línea incompleta', { vistaPrevia: calcularVistaPrevia([{ ...CAJA_X12_CON_IVA, valor: '' }], [CONTEXTO_CAJA_X12]) }],
    ['con total de factura vacío', { totalFactura: '' }],
    ['con total de factura cero', { totalFactura: '0' }],
    ['con total de factura inválido', { totalFactura: 'abc' }],
  ])('no se puede confirmar %s', (_nombre, cambio) => {
    expect(puedeConfirmar({ ...base, ...cambio })).toBe(false)
  })

  describe('de contado (INV-08)', () => {
    const contado = (medios: { medioPagoId: string; importe: string; referencia: string }[]) => ({
      ...base,
      formulario: { ...base.formulario, condicion: 'CONTADO' as const, medios },
    })

    it('con medios que suman el total se puede', () => {
      expect(puedeConfirmar(contado([{ medioPagoId: MEDIO, importe: '18000.00', referencia: '' }]))).toBe(true)
    })

    it('con faltante, con sobrante o sin medios no se puede', () => {
      expect(puedeConfirmar(contado([{ medioPagoId: MEDIO, importe: '17999.99', referencia: '' }]))).toBe(false)
      expect(puedeConfirmar(contado([{ medioPagoId: MEDIO, importe: '18000.01', referencia: '' }]))).toBe(false)
      expect(puedeConfirmar(contado([]))).toBe(false)
    })

    it('un medio sin elegir o un medio que exige referencia sin ella impide confirmar', () => {
      expect(puedeConfirmar(contado([{ medioPagoId: '', importe: '18000.00', referencia: '' }]))).toBe(false)
      const exigeReferencia = {
        ...contado([{ medioPagoId: MEDIO, importe: '18000.00', referencia: ' ' }]),
        mediosRequierenReferencia: new Set([MEDIO]),
      }
      expect(puedeConfirmar(exigeReferencia)).toBe(false)
      expect(
        puedeConfirmar({
          ...exigeReferencia,
          formulario: {
            ...exigeReferencia.formulario,
            medios: [{ medioPagoId: MEDIO, importe: '18000.00', referencia: 'op 123' }],
          },
        }),
      ).toBe(true)
    })
  })
})
