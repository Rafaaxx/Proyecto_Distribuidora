/**
 * Change 18b, tarea 13.1: funciones de dominio del pedido con descuentos (cuál porcentaje rige por
 * línea, mayor porcentaje manual, necesidad de autorización con el tope del contexto) — DSC-05,
 * DSC-06, DSC-07, DSC-08, INV-03; `design.md` D11, D15, D20. La pantalla solo las pinta.
 */

import { describe, expect, it } from 'vitest'

import {
  aplicarDescuentosAlPedido,
  reglaDelMotorDesdeApi,
  avisoDeTope,
  leerPorcentaje,
  mayorPorcentajeManual,
  necesidadDeAutorizacionDeDescuento,
  porcentajeQueRige,
  textoDePorcentajeQueRige,
  type ContextoDeDescuento,
  type DescuentoDeLinea,
} from '../../../../src/domain/ventas/descuentosDeVenta'

const VENDEDOR: ContextoDeDescuento = {
  habilitado: true,
  motivoObligatorio: false,
  tienePermiso: true,
  tope: '0.050000',
  puedeAutorizar: false,
}

describe('leerPorcentaje', () => {
  it.each([
    ['5', '0.050000'],
    ['7,5', '0.075000'],
    ['7.5', '0.075000'],
    ['100', '1.000000'],
    ['0,0001', '0.000001'],
    ['  10 ', '0.100000'],
  ])('"%s" se lee como la fracción %s', (texto, esperado) => {
    expect(leerPorcentaje(texto)).toEqual({ valido: true, fraccion: esperado })
  })

  it('un campo vacío es "sin porcentaje", no un error', () => {
    expect(leerPorcentaje('')).toEqual({ valido: true, fraccion: null })
    expect(leerPorcentaje('   ')).toEqual({ valido: true, fraccion: null })
  })

  it.each(['0', '0,0', '100,01', '101', '-5', 'abc', '5%', '1,23456', '1e2', '5,'])(
    '"%s" no es un porcentaje válido (mayor que 0 y hasta 100, hasta 4 decimales)',
    (texto) => {
      const r = leerPorcentaje(texto)
      expect(r.valido).toBe(false)
      if (!r.valido) expect(r.mensaje).toMatch(/mayor que 0 y hasta 100/)
    },
  )
})

describe('porcentajeQueRige (DSC-05, DSC-08)', () => {
  it('el propio reemplaza al general, sea mayor o menor', () => {
    expect(porcentajeQueRige('0.050000', '0.100000')).toEqual({ fraccion: '0.100000', origen: 'propio' })
    expect(porcentajeQueRige('0.050000', '0.020000')).toEqual({ fraccion: '0.020000', origen: 'propio' })
  })

  it('sin propio rige el general; sin ninguno no rige nada', () => {
    expect(porcentajeQueRige('0.050000', null)).toEqual({ fraccion: '0.050000', origen: 'general' })
    expect(porcentajeQueRige(null, null)).toEqual({ fraccion: null, origen: null })
  })

  it('se muestra con la marca de cuál rige', () => {
    expect(textoDePorcentajeQueRige({ fraccion: '0.100000', origen: 'propio' })).toBe('10 % (propio)')
    expect(textoDePorcentajeQueRige({ fraccion: '0.075000', origen: 'general' })).toBe('7,5 % (general)')
    expect(textoDePorcentajeQueRige({ fraccion: null, origen: null })).toBe('')
  })
})

describe('mayorPorcentajeManual (DSC-06)', () => {
  it('es el más alto que quedó en alguna línea, comparado como número exacto', () => {
    expect(mayorPorcentajeManual(['0.050000', '0.080000', null])).toBe('0.080000')
    expect(mayorPorcentajeManual(['0.1', '0.100000'])).toBe('0.1')
  })

  it('sin porcentajes manuales es nulo', () => {
    expect(mayorPorcentajeManual([])).toBeNull()
    expect(mayorPorcentajeManual([null, null])).toBeNull()
  })
})

describe('necesidadDeAutorizacionDeDescuento (DSC-06)', () => {
  it('sin porcentaje manual no hay nada que autorizar', () => {
    expect(necesidadDeAutorizacionDeDescuento(null, VENDEDOR)).toEqual({ estado: 'sin-descuento' })
  })

  it('justo en el tope pasa directo; un poco más pide autorizador', () => {
    expect(necesidadDeAutorizacionDeDescuento('0.050000', VENDEDOR)).toEqual({
      estado: 'dentro-del-tope',
      tope: '0.050000',
    })
    expect(necesidadDeAutorizacionDeDescuento('0.050001', VENDEDOR)).toEqual({
      estado: 'requiere-autorizador',
      tope: '0.050000',
    })
  })

  it('quien tiene el permiso de autorizar se autoriza solo (permiso propio)', () => {
    expect(necesidadDeAutorizacionDeDescuento('0.080000', { ...VENDEDOR, puedeAutorizar: true })).toEqual({
      estado: 'permiso-propio',
      tope: '0.050000',
    })
  })

  it('con el descuento manual deshabilitado o sin DESCUENTO_MANUAL no se puede dar ninguno', () => {
    expect(necesidadDeAutorizacionDeDescuento('0.010000', { ...VENDEDOR, habilitado: false })).toEqual({
      estado: 'deshabilitado',
    })
    expect(
      necesidadDeAutorizacionDeDescuento('0.010000', { ...VENDEDOR, tienePermiso: false, tope: null }),
    ).toEqual({ estado: 'sin-permiso' })
  })

  it('el Administrador (tope 100 %) nunca necesita autorización', () => {
    expect(necesidadDeAutorizacionDeDescuento('1.000000', { ...VENDEDOR, tope: '1.000000' })).toEqual({
      estado: 'dentro-del-tope',
      tope: '1.000000',
    })
  })
})

describe('avisoDeTope (D15)', () => {
  it('Pedro ve su tope y que más pide autorización', () => {
    expect(avisoDeTope(VENDEDOR)).toBe('Podés descontar hasta 5 %; más pide autorización.')
  })

  it('el Administrador ve que puede hasta 100 %', () => {
    expect(avisoDeTope({ ...VENDEDOR, tope: '1.000000', puedeAutorizar: true })).toBe(
      'Podés descontar hasta 100 %.',
    )
  })

  it('quien autoriza ve que lo que pase de su tope lo autoriza él', () => {
    expect(avisoDeTope({ ...VENDEDOR, puedeAutorizar: true })).toBe(
      'Podés descontar hasta 5 %; más lo autorizás vos con tu permiso.',
    )
  })

  it('sin permiso o con el descuento deshabilitado lo dice', () => {
    expect(avisoDeTope({ ...VENDEDOR, tienePermiso: false, tope: null })).toBe(
      'No podés dar descuentos manuales.',
    )
    expect(avisoDeTope({ ...VENDEDOR, habilitado: false })).toBe(
      'La empresa no permite descuentos manuales por ahora.',
    )
  })
})

describe('aplicarDescuentosAlPedido (DSC-05, DSC-07, INV-14)', () => {
  const lineas = [
    { lineaId: 'a', bruto: '31250.00', propio: null },
    { lineaId: 'b', bruto: '10000.00', propio: null },
  ]

  it('sin descuentos el neto es el bruto y el total es la suma', () => {
    const r = aplicarDescuentosAlPedido(lineas, null, null)
    expect(r.total).toBe('41250.00')
    expect(r.mayorManual).toBeNull()
    expect(r.lineas.map((l) => [l.descuentos.length, l.descuentoTotal, l.neto])).toEqual([
      [0, '0.00', '31250.00'],
      [0, '0.00', '10000.00'],
    ])
  })

  it('el general se aplica a todas las líneas, redondeado línea por línea (ROUND_HALF_UP)', () => {
    const r = aplicarDescuentosAlPedido(
      [
        { lineaId: 'a', bruto: '0.25', propio: null },
        { lineaId: 'b', bruto: '0.25', propio: null },
      ],
      '0.500000',
      null,
    )
    // 0,125 -> 0,13 en cada línea (mitad hacia arriba), no 0,25 sobre el total.
    expect(r.lineas.map((l) => l.descuentoTotal)).toEqual(['0.13', '0.13'])
    expect(r.total).toBe('0.24')
  })

  it('el propio reemplaza al general: 5 % general y 10 % en el vino', () => {
    const r = aplicarDescuentosAlPedido(
      [
        { lineaId: 'vino', bruto: '31250.00', propio: '0.100000' },
        { lineaId: 'otro', bruto: '10000.00', propio: null },
      ],
      '0.050000',
      null,
    )
    expect(r.lineas[0]?.descuentos).toEqual([
      { origen: 'MANUAL', reglaId: null, porcentaje: '0.100000', importe: '3125.00' },
    ])
    expect(r.lineas[1]?.descuentos).toEqual([
      { origen: 'MANUAL', reglaId: null, porcentaje: '0.050000', importe: '500.00' },
    ])
    expect(r.lineas[0]?.rige).toEqual({ fraccion: '0.100000', origen: 'propio' })
    expect(r.lineas[1]?.rige).toEqual({ fraccion: '0.050000', origen: 'general' })
    expect(r.mayorManual).toBe('0.100000')
    expect(r.total).toBe('37625.00')
  })

  it('un manual que redondea a cero no se informa (DSC-07)', () => {
    const r = aplicarDescuentosAlPedido([{ lineaId: 'a', bruto: '0.04', propio: null }], '0.100000', null)
    expect(r.lineas[0]?.descuentos).toEqual([])
    expect(r.mayorManual).toBeNull()
  })

  it('usa los descuentos que resolvió el servidor (automáticos incluidos) y el neto sale de ellos', () => {
    const automatico: DescuentoDeLinea = {
      origen: 'AUTOMATICO',
      reglaId: 'r1',
      porcentaje: '0.050000',
      importe: '1562.50',
    }
    const manual: DescuentoDeLinea = { origen: 'MANUAL', reglaId: null, porcentaje: '0.080000', importe: '2375.00' }
    const r = aplicarDescuentosAlPedido(
      [{ lineaId: 'a', bruto: '31250.00', propio: null }],
      '0.080000',
      new Map([['a', [automatico, manual]]]),
    )
    expect(r.lineas[0]?.descuentoTotal).toBe('3937.50')
    expect(r.lineas[0]?.neto).toBe('27312.50')
    expect(r.total).toBe('27312.50')
    expect(r.mayorManual).toBe('0.080000')
  })

  it('el total nunca pasa por number: importes grandes con centavos quedan exactos', () => {
    const r = aplicarDescuentosAlPedido([{ lineaId: 'a', bruto: '99999999999.99', propio: '0.010000' }], null, null)
    expect(r.lineas[0]?.descuentoTotal).toBe('1000000000.00')
    expect(r.total).toBe('98999999999.99')
  })
})

describe('descuentos automáticos con la gemela del motor (DSC-05, ADR-050)', () => {
  const REGLA_API = {
    id: 'r-volumen',
    nombre: 'Volumen vinos',
    tipo: 'VOLUMEN_OPERACION',
    medida: 'IMPORTE_BRUTO',
    operador: 'GTE',
    umbral: '10000.00',
    accion_tipo: 'PORCENTAJE',
    accion_porcentaje: '0.050000',
    accion_importe: null,
    acumulable: false,
    prioridad: 1,
    alcances: [],
  } as const
  const motor = (productoId: string) => ({
    cantidadBase: 6,
    unidadesReferencia: 6,
    productoId,
    categoriaId: 'cat',
    marcaId: 'marca',
  })

  it('reglaDelMotorDesdeApi pasa la regla de la API (snake_case, texto) a la del motor', () => {
    expect(reglaDelMotorDesdeApi(REGLA_API)).toEqual({
      id: 'r-volumen',
      tipo: 'VOLUMEN_OPERACION',
      medida: 'IMPORTE_BRUTO',
      operador: 'GTE',
      umbral: '10000.00',
      accionTipo: 'PORCENTAJE',
      accionPorcentaje: '0.050000',
      accionImporte: null,
      acumulable: false,
      prioridad: 1,
      alcances: [],
    })
    expect(
      reglaDelMotorDesdeApi({ ...REGLA_API, alcances: [{ tipo: 'MARCA', entidad_id: 'm1' }] }).alcances,
    ).toEqual([{ tipo: 'MARCA', entidadId: 'm1' }])
  })

  it('la regla de volumen deja el descuento automático en cada línea y el neto lo refleja', () => {
    const r = aplicarDescuentosAlPedido(
      [
        { lineaId: 'a', bruto: '25000.00', propio: null, motor: motor('p1') },
        { lineaId: 'b', bruto: '6250.00', propio: null, motor: motor('p1') },
      ],
      null,
      null,
      [reglaDelMotorDesdeApi(REGLA_API)],
    )
    expect(r.lineas[0]?.descuentos).toEqual([
      { origen: 'AUTOMATICO', reglaId: 'r-volumen', porcentaje: '0.050000', importe: '1250.00' },
    ])
    expect(r.lineas[1]?.descuentos[0]?.importe).toBe('312.50')
    expect(r.total).toBe('29687.50')
    expect(r.mayorManual).toBeNull()
  })

  it('el manual se aplica después, sobre lo que dejó el automático; el propio es solo de su línea', () => {
    const r = aplicarDescuentosAlPedido(
      [
        { lineaId: 'a', bruto: '25000.00', propio: '0.100000', motor: motor('p1') },
        { lineaId: 'b', bruto: '6250.00', propio: null, motor: motor('p1') },
      ],
      null,
      null,
      [reglaDelMotorDesdeApi(REGLA_API)],
    )
    // 25.000 - 1.250 (5 %) = 23.750; 10 % de eso = 2.375.
    expect(r.lineas[0]?.descuentos.map((d) => [d.origen, d.importe])).toEqual([
      ['AUTOMATICO', '1250.00'],
      ['MANUAL', '2375.00'],
    ])
    expect(r.lineas[1]?.descuentos.map((d) => d.origen)).toEqual(['AUTOMATICO'])
    expect(r.mayorManual).toBe('0.100000')
  })

  it('una venta que no alcanza el umbral no lleva automático; sin reglas da lo mismo que antes', () => {
    const chica = [{ lineaId: 'a', bruto: '5000.00', propio: null, motor: motor('p1') }]
    expect(aplicarDescuentosAlPedido(chica, null, null, [reglaDelMotorDesdeApi(REGLA_API)]).lineas[0]?.descuentos).toEqual([])
    expect(aplicarDescuentosAlPedido(chica, null, null, []).total).toBe('5000.00')
  })

  it('los descuentos del servidor (DESCUENTO_DIFIERE aceptado) mandan sobre el cálculo local', () => {
    const delServidor: DescuentoDeLinea = { origen: 'AUTOMATICO', reglaId: 'otra', porcentaje: '0.100000', importe: '2500.00' }
    const r = aplicarDescuentosAlPedido(
      [{ lineaId: 'a', bruto: '25000.00', propio: null, motor: motor('p1') }],
      null,
      new Map([['a', [delServidor]]]),
      [reglaDelMotorDesdeApi(REGLA_API)],
    )
    expect(r.lineas[0]?.descuentos).toEqual([delServidor])
    expect(r.total).toBe('22500.00')
  })
})
