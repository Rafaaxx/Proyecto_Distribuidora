import { describe, expect, it } from 'vitest'

import { armarConfirmacionDeRuta, armarVentaDeRuta } from '../../../../src/domain/ruta/armadoDeVentaLocal'
import { MENSAJE_ACTUALIZAR_DATOS_POR_STOCK } from '../../../../src/domain/ruta/stockDeVenta'
import { FALTA_CONTADO_DE_CONSUMIDOR_FINAL } from '../../../../src/domain/ventas/calculoDeVenta'
import { ID } from '../../utils/bootstrapDePrueba'
import {
  bootstrapParaVender,
  carritoDePrueba,
  datosParaVenderDesde,
  IDS_DE_PRUEBA as IDS,
} from '../../utils/datosParaVender'

/**
 * Change 22a, tareas 10.1 y 10.2 (lógica de la pantalla de venta; spec `ventas/venta-en-ruta`;
 * `design.md` D1, D6 a D10; cita PRC-22, VTA-04, DSC-05, DSC-06, CLI-02, CLI-03, CRE-06, CRE-07,
 * STK-06, INV-03, INV-04). Todo el armado vive en funciones puras: los componentes solo lo pintan.
 */
const AHORA = new Date('2026-10-30T15:00:00.000Z')
const MEDIO = { medioPagoId: IDS.efectivo, importe: '120000.00', referencia: '' }

describe('armar la venta de ruta: pedido, precios y totales (PRC-22, VTA-04)', () => {
  it('2 cajas + 3 unidades de Gaseosa: dos líneas con bruto exacto y total $120.000,00', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(bootstrapParaVender()), carritoDePrueba(), AHORA)

    expect(armada.lineas.map((l) => [l.lineaId, l.cantidad, l.cantidadBase, l.bruto])).toEqual([
      ['linea-caja', 2, 12, '96000.00'],
      ['linea-unidad', 3, 3, '24000.00'],
    ])
    expect(armada.total).toBe('120000.00')
    expect(armada.puedeConfirmar).toBe(true)
  })

  it('otro pedido: 1 caja suelta a $48.000,00 y sin cobro; el saldo resultante suma al saldo del bootstrap', () => {
    const carrito = carritoDePrueba({
      items: [{ productoId: IDS.producto, cajas: 1, unidades: 0, idsDeLinea: { [IDS.caja]: 'l1' } }],
    })

    const armada = armarVentaDeRuta(datosParaVenderDesde(bootstrapParaVender()), carrito, AHORA)

    expect(armada.total).toBe('48000.00')
    expect(armada.saldoConsiderado).toBe('1500.50')
    expect(armada.saldoResultante).toBe('49500.50')
  })

  it('sin productos no se puede confirmar', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(bootstrapParaVender()), carritoDePrueba({ items: [] }), AHORA)

    expect(armada.puedeConfirmar).toBe(false)
    expect(armada.total).toBe('0.00')
  })

  it('el saldo considerado suma las ventas locales de la jornada (CRE-08)', () => {
    const b = bootstrapParaVender()
    const datos = datosParaVenderDesde(b, [
      {
        operation_id: 'o',
        jornada_id: b.sesion.jornada.id,
        tipo: 'VENTA_DEBITO',
        producto_id: null,
        cliente_id: IDS.cliente,
        cantidad_base: null,
        importe: '70000.00',
        estado_operacion: 'PENDIENTE',
      },
    ])

    expect(armarVentaDeRuta(datos, carritoDePrueba(), AHORA).saldoConsiderado).toBe('71500.50')
  })
})

describe('reglas del cliente y de la cobranza (CLI-02, CLI-03, VTA-11)', () => {
  it('cliente suspendido sin VENDER_CLIENTE_SUSPENDIDO: bloqueado con el texto de la spec', () => {
    const b = bootstrapParaVender((x) => {
      const c = x.clientes[0]
      if (c) c.estado = 'SUSPENDIDO'
    })

    const armada = armarVentaDeRuta(datosParaVenderDesde(b), carritoDePrueba({ medios: [MEDIO] }), AHORA)

    expect(armada.puedeConfirmar).toBe(false)
    expect(armada.bloqueos).toContain('El cliente está suspendido: no se le puede vender.')
  })

  it('con VENDER_CLIENTE_SUSPENDIDO se puede vender al suspendido', () => {
    const b = bootstrapParaVender((x) => {
      const c = x.clientes[0]
      if (c) c.estado = 'SUSPENDIDO'
      x.sesion.permisos = ['VENDER', 'VENDER_CLIENTE_SUSPENDIDO']
    })

    expect(armarVentaDeRuta(datosParaVenderDesde(b), carritoDePrueba(), AHORA).puedeConfirmar).toBe(true)
  })

  it('consumidor final con cobro parcial: bloqueado; con cobro igual al total: se confirma sin crédito', () => {
    const b = bootstrapParaVender((x) => {
      const c = x.clientes[0]
      if (c) c.es_consumidor_final = true
    })
    const datos = datosParaVenderDesde(b)

    const parcial = armarVentaDeRuta(datos, carritoDePrueba({ medios: [{ ...MEDIO, importe: '100000.00' }] }), AHORA)
    const exacto = armarVentaDeRuta(datos, carritoDePrueba({ medios: [MEDIO] }), AHORA)

    expect(parcial.puedeConfirmar).toBe(false)
    expect(parcial.bloqueos).toContain(FALTA_CONTADO_DE_CONSUMIDOR_FINAL)
    expect(exacto.puedeConfirmar).toBe(true)
    expect(exacto.panelDeCredito).toBeNull()
  })

  it('un medio que exige referencia sin referencia no deja confirmar', () => {
    const b = bootstrapParaVender((x) => {
      x.catalogos.medios_pago = [{ id: IDS.efectivo, nombre: 'Transferencia', requiere_referencia: true }]
    })
    const datos = datosParaVenderDesde(b)

    expect(armarVentaDeRuta(datos, carritoDePrueba({ medios: [MEDIO] }), AHORA).puedeConfirmar).toBe(false)
    expect(
      armarVentaDeRuta(datos, carritoDePrueba({ medios: [{ ...MEDIO, referencia: 'TRF-1' }] }), AHORA).puedeConfirmar,
    ).toBe(true)
  })
})

describe('stock del vehículo (D6 = C; STK-05, STK-06, INV-04)', () => {
  const pideTres = carritoDePrueba({
    items: [{ productoId: IDS.producto, cajas: 3, unidades: 3, idsDeLinea: { [IDS.caja]: 'a', [IDS.unidad]: 'b' } }],
  })

  it('sin PERMITIR_STOCK_NEGATIVO la venta que supera el stock (21 > 20 en unidad base) se bloquea', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(bootstrapParaVender()), pideTres, AHORA)

    expect(armada.stock.confirmacion).toBe('bloqueada')
    expect(armada.puedeConfirmar).toBe(false)
    expect(armada.bloqueos).toContain(MENSAJE_ACTUALIZAR_DATOS_POR_STOCK)
  })

  it('con el permiso avisa y exige "Vender igual" para confirmar', () => {
    const b = bootstrapParaVender((x) => {
      x.sesion.permisos = ['VENDER', 'PERMITIR_STOCK_NEGATIVO']
    })
    const datos = datosParaVenderDesde(b)

    const sin = armarVentaDeRuta(datos, pideTres, AHORA)
    const con = armarVentaDeRuta(datos, { ...pideTres, venderIgual: true }, AHORA)

    expect(sin.stock.confirmacion).toBe('vender-igual')
    expect(sin.puedeConfirmar).toBe(false)
    expect(con.puedeConfirmar).toBe(true)
  })

  it('las ventas locales de la jornada bajan el disponible (RUT-04)', () => {
    const b = bootstrapParaVender()
    const datos = datosParaVenderDesde(b, [
      {
        operation_id: 'o',
        jornada_id: b.sesion.jornada.id,
        tipo: 'VENTA_STOCK',
        producto_id: IDS.producto,
        cliente_id: null,
        cantidad_base: -10,
        importe: null,
        estado_operacion: 'PENDIENTE',
      },
    ])

    // 12 + 3 = 15 unidades base con 20 - 10 = 10 disponibles.
    expect(armarVentaDeRuta(datos, carritoDePrueba(), AHORA).stock.confirmacion).toBe('bloqueada')
  })
})

describe('crédito sin conexión (D9; CRE-04 a CRE-07, CRE-09)', () => {
  function conLimite(politica: string, limite: string, tolerancia: string | null) {
    return bootstrapParaVender((x) => {
      const c = x.clientes[0]
      if (c) {
        c.saldo = '0.00'
        c.credito = { limite, politica, tolerancia_tipo: tolerancia === null ? null : 'IMPORTE', tolerancia_valor: tolerancia }
      }
    })
  }

  it('dentro de la tolerancia (AUTORIZAR): se confirma por TOLERANCIA_OFFLINE', () => {
    // Total 120.000 con límite 110.000 y tolerancia 20.000: exceso 10.000.
    const armada = armarVentaDeRuta(datosParaVenderDesde(conLimite('AUTORIZAR', '110000.00', '20000.00')), carritoDePrueba(), AHORA)

    expect(armada.panelDeCredito?.decision).toBe('tolerancia-offline')
    expect(armada.puedeConfirmar).toBe(true)
  })

  it('fuera de la tolerancia pide autorizador y, sin supervisor elegido, no se confirma', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(conLimite('AUTORIZAR', '110000.00', '5000.00')), carritoDePrueba(), AHORA)

    expect(armada.panelDeCredito?.decision).toBe('pide-autorizador')
    expect(armada.autorizacionesNecesarias).toEqual(['CREDITO'])
    expect(armada.puedeConfirmar).toBe(false)
  })

  it('con supervisor elegido para el crédito la venta puede confirmar (el PIN se verifica al tocar Confirmar)', () => {
    const b = conLimite('AUTORIZAR', '110000.00', '5000.00')
    b.autorizadores = [
      { id: ID(60), nombre: 'Sup Uno', permisos: ['SUPERAR_CREDITO'], pin_hash: 'h', pin_sal: 's', iteraciones: 1 },
    ]
    const armada = armarVentaDeRuta(datosParaVenderDesde(b), carritoDePrueba({ seleccion: { CREDITO: ID(60) } }), AHORA)

    expect(armada.autorizadores.map((a) => a.id)).toEqual([ID(60)])
    expect(armada.puedeConfirmar).toBe(true)
  })

  it('BLOQUEAR bloquea el exceso (CRE-07) y ADVERTIR pide aceptarlo (CRE-04)', () => {
    const bloquear = armarVentaDeRuta(datosParaVenderDesde(conLimite('BLOQUEAR', '110000.00', null)), carritoDePrueba(), AHORA)
    const advertir = datosParaVenderDesde(conLimite('ADVERTIR', '110000.00', null))

    expect(bloquear.panelDeCredito?.decision).toBe('bloqueado')
    expect(bloquear.puedeConfirmar).toBe(false)
    expect(armarVentaDeRuta(advertir, carritoDePrueba(), AHORA).puedeConfirmar).toBe(false)
    expect(armarVentaDeRuta(advertir, carritoDePrueba({ aceptaExceso: true }), AHORA).puedeConfirmar).toBe(true)
  })
})

describe('descuentos y lista (DSC-05, DSC-06, PRC-21)', () => {
  const conDescuentos = (cambios: (b: ReturnType<typeof bootstrapParaVender>) => void = () => undefined) =>
    bootstrapParaVender((x) => {
      x.contexto_venta = {
        descuento_manual: { habilitado: true, motivo_obligatorio: false, tiene_permiso: true, tope: '0.100000', puede_autorizar: false },
        puede_superar_credito: false,
      }
      cambios(x)
    })

  it('5 % general dentro del tope: total 114.000,00 y la línea lleva su descuento manual', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(conDescuentos()), carritoDePrueba({ generalTexto: '5' }), AHORA)

    expect(armada.total).toBe('114000.00')
    expect(armada.lineas[0]?.descuentoTotal).toBe('4800.00')
    expect(armada.necesidadDeDescuento.estado).toBe('dentro-del-tope')
    expect(armada.puedeConfirmar).toBe(true)
  })

  it('sobre el tope sin permiso propio pide autorizador y sin supervisor no confirma', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(conDescuentos()), carritoDePrueba({ generalTexto: '15' }), AHORA)

    expect(armada.necesidadDeDescuento.estado).toBe('requiere-autorizador')
    expect(armada.autorizacionesNecesarias).toEqual(['DESCUENTO'])
    expect(armada.puedeConfirmar).toBe(false)
  })

  it('un porcentaje inválido bloquea', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(conDescuentos()), carritoDePrueba({ generalTexto: 'abc' }), AHORA)

    expect(armada.puedeConfirmar).toBe(false)
  })

  it('sin descuento manual habilitado el texto escrito no se aplica', () => {
    const armada = armarVentaDeRuta(datosParaVenderDesde(bootstrapParaVender()), carritoDePrueba({ generalTexto: '5' }), AHORA)

    expect(armada.total).toBe('120000.00')
  })

  it('otra lista sin USAR_LISTA_ANTERIOR se ignora; con el permiso y motivo exigido, sin motivo bloquea', () => {
    const b = bootstrapParaVender((x) => {
      x.configuracion.motivo_obligatorio_lista = true
      x.listas.push({ id: ID(70), nombre: 'Mayorista', es_predeterminada: false, versiones: [] })
    })
    const datos = datosParaVenderDesde(b)
    const carrito = carritoDePrueba({ listaId: ID(70) })

    const sinPermiso = armarVentaDeRuta(datos, carrito, AHORA)
    const conPermiso = armarVentaDeRuta(
      datosParaVenderDesde({ ...b, sesion: { ...b.sesion, permisos: ['VENDER', 'USAR_LISTA_ANTERIOR'] } }),
      carrito,
      AHORA,
    )

    expect(sinPermiso.lista.ofreceOtra).toBe(false)
    expect(sinPermiso.lineas.length).toBe(2)
    expect(conPermiso.lista.ofreceOtra).toBe(true)
    expect(conPermiso.bloqueos).toContain('Elegí el motivo para usar otra lista o una versión anterior.')
    // La lista elegida no tiene versiones: los productos quedan sin precio.
    expect(conPermiso.puedeConfirmar).toBe(false)
  })

  it('un producto sin precio en la versión no se puede vender', () => {
    const b = bootstrapParaVender((x) => {
      const version = x.listas[0]?.versiones[0]
      if (version) version.precios = []
    })

    const armada = armarVentaDeRuta(datosParaVenderDesde(b), carritoDePrueba(), AHORA)

    expect(armada.puedeConfirmar).toBe(false)
    expect(Object.values(armada.erroresPorProducto)[0]).toMatch(/sin precio/i)
  })
})

describe('armar la confirmación (D2, D9, D15; INV-03)', () => {
  const contexto = {
    usuarioId: ID(1),
    dispositivoId: 'disp-1',
    ahora: AHORA,
    appVersion: '1.0.0',
    autorizadoresVerificados: [] as string[],
  }

  it('arma contenido sin número definitivo, con total, cobranza, crédito completo y nota congelada', () => {
    const datos = datosParaVenderDesde(bootstrapParaVender())
    const carrito = carritoDePrueba({ medios: [{ ...MEDIO, importe: '20000.00' }], observacionCobranza: ' sin vuelto ' })
    const armada = armarVentaDeRuta(datos, carrito, AHORA)

    const entrada = armarConfirmacionDeRuta(datos, carrito, armada, contexto)

    expect(entrada.operationId).toBe('op-1')
    expect(entrada.contenido).toMatchObject({
      venta_id: 'venta-1',
      cliente_id: IDS.cliente,
      ubicacion_id: null,
      total: '120000.00',
      cobranza: {
        cobranza_id: 'cobranza-1',
        observacion: 'sin vuelto',
        medios: [{ medio_pago_id: IDS.efectivo, importe: '20000.00', referencia: null }],
      },
      credito: { saldo_considerado: '1500.50', resolucion: 'SIN_EXCESO', acepta_exceso: false },
    })
    expect(entrada.contenido.lineas.map((l) => [l.linea_id, l.cantidad, l.importe_bruto])).toEqual([
      ['linea-caja', 2, '96000.00'],
      ['linea-unidad', 3, '24000.00'],
    ])
    expect(entrada.lineas).toEqual([
      { lineaId: 'linea-caja', productoId: IDS.producto, cantidadBase: 12 },
      { lineaId: 'linea-unidad', productoId: IDS.producto, cantidadBase: 3 },
    ])
    expect(entrada.calculo.total.toFixed(2)).toBe('120000.00')
    expect(entrada.nota?.saldo_resultante).toBe('101500.50')
    expect(entrada.nota?.cliente.nombre).toBe('Almacén Uno')
    expect(entrada.nota?.lineas.map((l) => l.presentacion_nombre)).toEqual(['Caja x6', 'Unidad'])
  })

  it('el descuento manual viaja en el contenido y el autorizador verificado en el crédito', () => {
    const b = bootstrapParaVender((x) => {
      x.contexto_venta = {
        descuento_manual: { habilitado: true, motivo_obligatorio: true, tiene_permiso: true, tope: '0.100000', puede_autorizar: false },
        puede_superar_credito: false,
      }
      const c = x.clientes[0]
      if (c) {
        c.saldo = '0.00'
        c.credito = { limite: '110000.00', politica: 'AUTORIZAR', tolerancia_tipo: 'IMPORTE', tolerancia_valor: '1000.00' }
      }
      x.autorizadores = [
        { id: ID(60), nombre: 'Sup', permisos: ['SUPERAR_CREDITO'], pin_hash: 'h', pin_sal: 's', iteraciones: 1 },
      ]
    })
    const datos = datosParaVenderDesde(b)
    const carrito = carritoDePrueba({ generalTexto: '5', motivoDescuentoId: IDS.motivo, seleccion: { CREDITO: ID(60) } })
    // Total con 5 %: 114.000 contra límite 110.000 y tolerancia 1.000: exceso 4.000, fuera de la tolerancia.
    const armada = armarVentaDeRuta(datos, carrito, AHORA)

    const entrada = armarConfirmacionDeRuta(datos, carrito, armada, { ...contexto, autorizadoresVerificados: [ID(60)] })

    expect(entrada.contenido).toMatchObject({
      total: '114000.00',
      descuento_manual_general: '0.050000',
      motivo_descuento_id: IDS.motivo,
      credito: { resolucion: 'PIN_SUPERVISOR', acepta_exceso: true, autorizador_id: ID(60) },
    })
    expect(entrada.contenido.lineas[0]?.descuentos?.[0]).toMatchObject({ origen: 'MANUAL', importe: '4800.00' })
  })

  it('sin el PIN del supervisor verificado no arma la confirmación', () => {
    const b = bootstrapParaVender((x) => {
      const c = x.clientes[0]
      if (c) {
        c.saldo = '0.00'
        c.credito = { limite: '110000.00', politica: 'AUTORIZAR', tolerancia_tipo: null, tolerancia_valor: null }
      }
      x.autorizadores = [
        { id: ID(60), nombre: 'Sup', permisos: ['SUPERAR_CREDITO'], pin_hash: 'h', pin_sal: 's', iteraciones: 1 },
      ]
    })
    const datos = datosParaVenderDesde(b)
    const carrito = carritoDePrueba({ seleccion: { CREDITO: ID(60) } })
    const armada = armarVentaDeRuta(datos, carrito, AHORA)

    expect(() => armarConfirmacionDeRuta(datos, carrito, armada, contexto)).toThrow()
  })

  it('una venta que no se puede confirmar no se arma', () => {
    const datos = datosParaVenderDesde(bootstrapParaVender())
    const carrito = carritoDePrueba({ items: [] })
    const armada = armarVentaDeRuta(datos, carrito, AHORA)

    expect(() => armarConfirmacionDeRuta(datos, carrito, armada, contexto)).toThrow(/no se puede confirmar/i)
  })
})
