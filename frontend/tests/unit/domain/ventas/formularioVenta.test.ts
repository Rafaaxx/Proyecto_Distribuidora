import { describe, expect, it } from 'vitest'

import {
  aplicarValoresDelServidor,
  construirSolicitudDeVenta,
  diferenciasConElServidor,
  puedeConfirmarVenta,
  type FormularioDeVenta,
  type LineaDelPedido,
} from '../../../../src/domain/ventas/formularioVenta'

const VENTA_ID = '0191a000-0000-7000-8000-000000000001'
const COBRANZA_ID = '0191a000-0000-7000-8000-000000000002'
const CTX = { mediosQueRequierenReferencia: new Set(['m-transf']), ubicacionObligatoria: true }

const LINEA_CAJAS: LineaDelPedido = {
  lineaId: 'l1',
  productoId: 'prod-a',
  presentacionId: 'p-caja',
  cantidad: 2,
  listaVersionId: 'v2',
  precioReferencia: '12500.00',
  unidadesReferencia: 6,
  importeBruto: '25000.00',
}
const LINEA_BOTELLAS: LineaDelPedido = {
  ...LINEA_CAJAS,
  lineaId: 'l2',
  presentacionId: 'p-botella',
  cantidad: 3,
  importeBruto: '6250.00',
}

function formulario(campos: Partial<FormularioDeVenta> = {}): FormularioDeVenta {
  return {
    clienteId: 'cli-1',
    ubicacionId: 'ubi-1',
    numero: 'V01-000042',
    listaId: '',
    versionId: '',
    motivoId: '',
    observacionCobranza: '',
    medios: [],
    ...campos,
  }
}

describe('esquema del formulario de venta (VTA-02, VTA-06, VTA-11)', () => {
  it('una venta completa sin cobranza es válida', () => {
    expect(puedeConfirmarVenta(formulario(), [LINEA_CAJAS], CTX)).toBe(true)
  })

  it('sin cliente, sin líneas, sin ubicación o con número mal formado no se confirma', () => {
    expect(puedeConfirmarVenta(formulario({ clienteId: '' }), [LINEA_CAJAS], CTX)).toBe(false)
    expect(puedeConfirmarVenta(formulario(), [], CTX)).toBe(false)
    expect(puedeConfirmarVenta(formulario({ ubicacionId: '' }), [LINEA_CAJAS], CTX)).toBe(false)
    expect(puedeConfirmarVenta(formulario({ numero: 'V01-42' }), [LINEA_CAJAS], CTX)).toBe(false)
  })

  it('con jornada abierta la ubicación no se pide (D3)', () => {
    expect(puedeConfirmarVenta(formulario({ ubicacionId: '' }), [LINEA_CAJAS], { ...CTX, ubicacionObligatoria: false })).toBe(true)
  })

  it('cada medio necesita importe positivo con dos decimales y referencia si el medio la exige', () => {
    const efectivo = { medioPagoId: 'm-efec', importe: '1000', referencia: '' }
    expect(puedeConfirmarVenta(formulario({ medios: [efectivo] }), [LINEA_CAJAS], CTX)).toBe(true)
    expect(puedeConfirmarVenta(formulario({ medios: [{ ...efectivo, importe: '0' }] }), [LINEA_CAJAS], CTX)).toBe(false)
    expect(puedeConfirmarVenta(formulario({ medios: [{ ...efectivo, importe: '10.001' }] }), [LINEA_CAJAS], CTX)).toBe(false)
    const transf = { medioPagoId: 'm-transf', importe: '500', referencia: '' }
    expect(puedeConfirmarVenta(formulario({ medios: [transf] }), [LINEA_CAJAS], CTX)).toBe(false)
    expect(puedeConfirmarVenta(formulario({ medios: [{ ...transf, referencia: '0042' }] }), [LINEA_CAJAS], CTX)).toBe(true)
  })

  it('admite hasta 200 líneas y hasta 20 medios', () => {
    const lineas = (n: number) => Array.from({ length: n }, (_, i) => ({ ...LINEA_CAJAS, lineaId: `l${String(i)}` }))
    expect(puedeConfirmarVenta(formulario(), lineas(200), CTX)).toBe(true)
    expect(puedeConfirmarVenta(formulario(), lineas(201), CTX)).toBe(false)
    const medios = (n: number) => Array.from({ length: n }, () => ({ medioPagoId: 'm-efec', importe: '1', referencia: '' }))
    expect(puedeConfirmarVenta(formulario({ medios: medios(20) }), [LINEA_CAJAS], CTX)).toBe(true)
    expect(puedeConfirmarVenta(formulario({ medios: medios(21) }), [LINEA_CAJAS], CTX)).toBe(false)
  })
})

describe('cuerpo de VENTA_CONFIRMAR (D2)', () => {
  it('lleva lo que vio el usuario: líneas con sus valores esperados y el total', () => {
    const solicitud = construirSolicitudDeVenta(formulario(), [LINEA_CAJAS, LINEA_BOTELLAS], '31250.00', VENTA_ID, COBRANZA_ID, true)
    expect(solicitud).toEqual({
      venta_id: VENTA_ID,
      numero: 'V01-000042',
      cliente_id: 'cli-1',
      ubicacion_id: 'ubi-1',
      lista_id: null,
      lista_version_id: null,
      motivo_lista_id: null,
      lineas: [
        {
          linea_id: 'l1',
          producto_id: 'prod-a',
          presentacion_id: 'p-caja',
          cantidad: 2,
          lista_version_id: 'v2',
          precio_referencia: '12500.00',
          unidades_referencia: 6,
          importe_bruto: '25000.00',
        },
        {
          linea_id: 'l2',
          producto_id: 'prod-a',
          presentacion_id: 'p-botella',
          cantidad: 3,
          lista_version_id: 'v2',
          precio_referencia: '12500.00',
          unidades_referencia: 6,
          importe_bruto: '6250.00',
        },
      ],
      total: '31250.00',
      cobranza: null,
    })
  })

  it('con jornada abierta no manda ubicación; con otra lista y versión manda lista, versión y motivo', () => {
    const solicitud = construirSolicitudDeVenta(
      formulario({ listaId: 'lista-x', versionId: 'ver-1', motivoId: 'mot-1' }),
      [LINEA_CAJAS],
      '25000.00',
      VENTA_ID,
      COBRANZA_ID,
      false,
    )
    expect(solicitud.ubicacion_id).toBeNull()
    expect(solicitud.lista_id).toBe('lista-x')
    expect(solicitud.lista_version_id).toBe('ver-1')
    expect(solicitud.motivo_lista_id).toBe('mot-1')
  })

  it('la cobranza viaja con sus medios como string de dos decimales y sin referencia vacía (INV-03)', () => {
    const solicitud = construirSolicitudDeVenta(
      formulario({
        observacionCobranza: ' Pagó en mostrador ',
        medios: [
          { medioPagoId: 'm-efec', importe: '15000.5', referencia: '' },
          { medioPagoId: 'm-transf', importe: '4999.50', referencia: ' 0042 ' },
        ],
      }),
      [LINEA_CAJAS],
      '25000.00',
      VENTA_ID,
      COBRANZA_ID,
      true,
    )
    expect(solicitud.cobranza).toEqual({
      cobranza_id: COBRANZA_ID,
      observacion: 'Pagó en mostrador',
      medios: [
        { medio_pago_id: 'm-efec', importe: '15000.50', referencia: null },
        { medio_pago_id: 'm-transf', importe: '4999.50', referencia: '0042' },
      ],
    })
  })
})

describe('PRECIO_DIFIERE: valores del servidor (design D2)', () => {
  const DETALLE = {
    lineas: [
      { linea_id: 'l1', lista_version_id: 'v3', precio_referencia: '13000.00', unidades_referencia: 6, importe_bruto: '26000.00' },
      { linea_id: 'l2', lista_version_id: 'v3', precio_referencia: '13000.00', unidades_referencia: 6, importe_bruto: '6500.00' },
    ],
    total: '32500.00',
  }

  it('reemplaza los valores esperados de cada línea por los del servidor, por identificador', () => {
    const resultado = aplicarValoresDelServidor([LINEA_BOTELLAS, LINEA_CAJAS], DETALLE)
    expect(resultado.total).toBe('32500.00')
    expect(resultado.lineas.map((l) => [l.lineaId, l.precioReferencia, l.importeBruto, l.listaVersionId])).toEqual([
      ['l2', '13000.00', '6500.00', 'v3'],
      ['l1', '13000.00', '26000.00', 'v3'],
    ])
    expect(resultado.lineas[0]?.cantidad).toBe(3)
  })

  it('una línea que el servidor no menciona queda como estaba', () => {
    const [segunda] = DETALLE.lineas.slice(1)
    const resultado = aplicarValoresDelServidor([LINEA_CAJAS], { lineas: segunda ? [segunda] : [], total: '6500.00' })
    expect(resultado.lineas[0]?.importeBruto).toBe('25000.00')
  })
})

describe('diferencias con lo que vio el usuario (D2)', () => {
  const DETALLE = {
    lineas: [
      { linea_id: 'l1', lista_version_id: 'v3', precio_referencia: '13000.00', unidades_referencia: 6, importe_bruto: '26000.00' },
      { linea_id: 'l2', lista_version_id: 'v2', precio_referencia: '12500.00', unidades_referencia: 6, importe_bruto: '6250.00' },
    ],
    total: '32250.00',
  }

  it('lista, por línea, el precio y el bruto de antes y de ahora, y marca cuáles cambiaron', () => {
    const diferencias = diferenciasConElServidor([LINEA_CAJAS, LINEA_BOTELLAS], DETALLE)
    expect(diferencias).toEqual([
      { lineaId: 'l1', precioAnterior: '12500.00', precioNuevo: '13000.00', brutoAnterior: '25000.00', brutoNuevo: '26000.00', cambio: true },
      { lineaId: 'l2', precioAnterior: '12500.00', precioNuevo: '12500.00', brutoAnterior: '6250.00', brutoNuevo: '6250.00', cambio: false },
    ])
  })

  it('un cambio solo de versión (mismo precio y bruto) también cuenta como cambio', () => {
    const [primera] = diferenciasConElServidor([LINEA_CAJAS], {
      lineas: [{ linea_id: 'l1', lista_version_id: 'v9', precio_referencia: '12500.00', unidades_referencia: 6, importe_bruto: '25000.00' }],
      total: '25000.00',
    })
    expect(primera?.cambio).toBe(true)
  })
})

describe('cuerpo de VENTA_CONFIRMAR con descuentos y crédito (change 18b, D1, D2)', () => {
  const vacio = {
    descuentoGeneral: null,
    motivoDescuentoId: null,
    descuentoAutorizadorId: null,
    aceptaExceso: false,
    creditoAutorizadorId: null,
    porLinea: new Map(),
  }

  it('sin extras (o con extras vacíos) el cuerpo es el de siempre: la huella no cambia', () => {
    const base = construirSolicitudDeVenta(formulario(), [LINEA_CAJAS], '25000.00', VENTA_ID, COBRANZA_ID, true)
    const conVacios = construirSolicitudDeVenta(formulario(), [LINEA_CAJAS], '25000.00', VENTA_ID, COBRANZA_ID, true, vacio)
    expect(conVacios).toEqual(base)
    expect(JSON.stringify(conVacios)).not.toContain('descuento')
    expect(JSON.stringify(conVacios)).not.toContain('credito')
  })

  it('lleva el general, el motivo, el autorizador y, por línea, el propio y los descuentos esperados como texto', () => {
    const solicitud = construirSolicitudDeVenta(formulario(), [LINEA_CAJAS, LINEA_BOTELLAS], '28125.00', VENTA_ID, COBRANZA_ID, true, {
      ...vacio,
      descuentoGeneral: '0.050000',
      motivoDescuentoId: 'mot-1',
      descuentoAutorizadorId: 'marta',
      porLinea: new Map([
        ['l1', { propio: '0.100000', descuentos: [{ origen: 'MANUAL' as const, reglaId: null, porcentaje: '0.100000', importe: '2500.00' }] }],
        [
          'l2',
          {
            propio: null,
            descuentos: [
              { origen: 'AUTOMATICO' as const, reglaId: 'r1', porcentaje: '0.050000', importe: '312.50' },
              { origen: 'MANUAL' as const, reglaId: null, porcentaje: '0.050000', importe: '296.88' },
            ],
          },
        ],
      ]),
    })
    expect(solicitud.descuento_manual_general).toBe('0.050000')
    expect(solicitud.motivo_descuento_id).toBe('mot-1')
    expect(solicitud.descuento_autorizador_id).toBe('marta')
    expect(solicitud.lineas[0]).toMatchObject({
      descuento_manual: '0.100000',
      descuentos: [{ origen: 'MANUAL', regla_id: null, porcentaje: '0.100000', importe: '2500.00' }],
    })
    expect(solicitud.lineas[1]?.descuento_manual).toBeUndefined()
    expect(solicitud.lineas[1]?.descuentos).toEqual([
      { origen: 'AUTOMATICO', regla_id: 'r1', porcentaje: '0.050000', importe: '312.50' },
      { origen: 'MANUAL', regla_id: null, porcentaje: '0.050000', importe: '296.88' },
    ])
  })

  it('el crédito viaja solo si hay algo que decir: la aceptación del exceso y/o el supervisor', () => {
    const armar = (extras: Partial<typeof vacio>) =>
      construirSolicitudDeVenta(formulario(), [LINEA_CAJAS], '25000.00', VENTA_ID, COBRANZA_ID, true, { ...vacio, ...extras }).credito
    expect(armar({})).toBeUndefined()
    expect(armar({ aceptaExceso: true })).toEqual({ acepta_exceso: true })
    expect(armar({ creditoAutorizadorId: 'julia' })).toEqual({ acepta_exceso: false, autorizador_id: 'julia' })
  })

  it('nunca incluye credenciales ni PIN: el PIN no es parte del contenido (D2)', () => {
    const solicitud = construirSolicitudDeVenta(formulario(), [LINEA_CAJAS], '25000.00', VENTA_ID, COBRANZA_ID, true, {
      ...vacio,
      descuentoAutorizadorId: 'marta',
    })
    expect(JSON.stringify(solicitud)).not.toMatch(/credenciales|pin/i)
  })
})
