import { describe, expect, it } from 'vitest'

import {
  agregarMedio,
  agregarProducto,
  cambiarCantidades,
  cambiarMedio,
  carritoNuevo,
  clientesParaElegir,
  hayLineas,
  leerCantidad,
  presentacionesDeVenta,
  productosOfrecidos,
  quitarMedio,
  quitarProducto,
} from '../../../../src/domain/ruta/carritoDeRuta'
import { MENSAJE_SIN_PRECIO } from '../../../../src/domain/ventas/pedido'
import { clienteDePrueba, ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender, datosParaVenderDesde, IDS_DE_PRUEBA as IDS } from '../../utils/datosParaVender'

/**
 * Change 22a, tarea 10.1 (el carrito en memoria de la pantalla de venta; `design.md` D12, D14;
 * VTA-02, VTA-07, VTA-10, CAT-07, CAT-08, INV-04): operaciones puras sobre el carrito y buscador
 * de productos con el precio de la versión de la venta.
 */
let n = 0
const nuevoId = () => `id-${++n}`

const caja = { presentacionId: IDS.caja, nombre: 'Caja x6', unidadesBase: 6, esReferencia: true }
const unidad = { presentacionId: IDS.unidad, nombre: 'Unidad', unidadesBase: 1, esReferencia: false }

describe('carrito de la venta de ruta (VTA-07)', () => {
  it('nace vacío con identificadores propios de la venta, la cobranza y el comando', () => {
    const carrito = carritoNuevo('cli', nuevoId)

    expect(carrito.clienteId).toBe('cli')
    expect(carrito.items).toEqual([])
    expect(new Set([carrito.ventaId, carrito.cobranzaId, carrito.operationId]).size).toBe(3)
    expect(hayLineas(carrito)).toBe(false)
  })

  it('agrega un producto que se vende por caja con 1 caja y uno solo en unidades con 1 unidad (CAT-07)', () => {
    const base = carritoNuevo('cli', nuevoId)

    const conCaja = agregarProducto(base, { productoId: 'p1', presentaciones: [caja, unidad] }, nuevoId)
    const conUnidad = agregarProducto(base, { productoId: 'p2', presentaciones: [unidad] }, nuevoId)

    expect(conCaja.items[0]).toMatchObject({ productoId: 'p1', cajas: 1, unidades: 0 })
    expect(Object.keys(conCaja.items[0]?.idsDeLinea ?? {})).toEqual([IDS.caja, IDS.unidad])
    expect(conUnidad.items[0]).toMatchObject({ productoId: 'p2', cajas: 0, unidades: 1 })
    expect(hayLineas(conCaja)).toBe(true)
  })

  it('no agrega dos veces el mismo producto', () => {
    const una = agregarProducto(carritoNuevo('cli', nuevoId), { productoId: 'p1', presentaciones: [caja] }, nuevoId)

    expect(agregarProducto(una, { productoId: 'p1', presentaciones: [caja] }, nuevoId).items).toHaveLength(1)
  })

  it('cambia las cantidades y quita el producto sin tocar lo demás', () => {
    let carrito = agregarProducto(carritoNuevo('cli', nuevoId), { productoId: 'p1', presentaciones: [caja, unidad] }, nuevoId)
    carrito = agregarProducto(carrito, { productoId: 'p2', presentaciones: [unidad] }, nuevoId)

    carrito = cambiarCantidades(carrito, 'p1', { cajas: 2, unidades: 3 })
    expect(carrito.items.map((i) => [i.productoId, i.cajas, i.unidades])).toEqual([
      ['p1', 2, 3],
      ['p2', 0, 1],
    ])

    carrito = quitarProducto(carrito, 'p1')
    expect(carrito.items.map((i) => i.productoId)).toEqual(['p2'])
  })

  it('agrega, cambia y quita medios de cobro', () => {
    let carrito = agregarMedio(carritoNuevo('cli', nuevoId))
    carrito = agregarMedio(carrito)
    expect(carrito.medios).toEqual([
      { medioPagoId: '', importe: '', referencia: '' },
      { medioPagoId: '', importe: '', referencia: '' },
    ])

    carrito = cambiarMedio(carrito, 1, { medioPagoId: 'm1', importe: '100.00' })
    expect(carrito.medios[1]).toEqual({ medioPagoId: 'm1', importe: '100.00', referencia: '' })

    carrito = quitarMedio(carrito, 0)
    expect(carrito.medios).toEqual([{ medioPagoId: 'm1', importe: '100.00', referencia: '' }])
  })
})

describe('leerCantidad: enteros no negativos (INV-04)', () => {
  it.each([
    ['3', 3],
    ['0', 0],
    ['', 0],
    ['-2', 0],
    ['2,5', 0],
    ['abc', 0],
    [' 12 ', 12],
  ])('"%s" -> %d', (texto, esperado) => {
    expect(leerCantidad(texto)).toBe(esperado)
  })
})

describe('productos que se ofrecen con el precio de la versión (PRC-22, VTA-10)', () => {
  const datos = datosParaVenderDesde(bootstrapParaVender())
  const version = datos.versiones[0]?.id ?? ''

  it('muestra el precio por presentación de la versión de la venta: caja $48.000,00 y unidad $8.000,00', () => {
    const [gaseosa] = productosOfrecidos(datos, version, '')

    expect(gaseosa).toMatchObject({ id: IDS.producto, nombre: 'Gaseosa', conPrecio: true, mensaje: null })
    expect(gaseosa?.presentaciones.map((p) => [p.nombre, p.precio])).toEqual([
      ['Unidad', '8000.00'],
      ['Caja x6', '48000.00'],
    ])
  })

  it('filtra por nombre o código sin importar mayúsculas ni tildes', () => {
    expect(productosOfrecidos(datos, version, 'GASEO')).toHaveLength(1)
    expect(productosOfrecidos(datos, version, 'p1')).toHaveLength(1)
    expect(productosOfrecidos(datos, version, 'cerveza')).toHaveLength(0)
  })

  it('un producto sin precio en la versión no se puede agregar y dice por qué (VTA-10)', () => {
    const sinPrecios = { ...datos, precios: [] }

    const [gaseosa] = productosOfrecidos(sinPrecios, version, '')

    expect(gaseosa).toMatchObject({ conPrecio: false, mensaje: MENSAJE_SIN_PRECIO })
  })

  it('sin versión vigente ningún producto tiene precio', () => {
    const [gaseosa] = productosOfrecidos(datos, '', '')

    expect(gaseosa?.conPrecio).toBe(false)
  })
})

describe('clientes para elegir con su saldo y crédito local (CRE-01, CRE-08, RUT-04)', () => {
  it('pone la cartera antes que el resto y calcula saldo considerado y disponible con las ventas locales', () => {
    const b = bootstrapParaVender((x) => {
      const fuera = { ...clienteDePrueba(2, 'Bazar Dos'), en_cartera: false }
      const propio = { ...clienteDePrueba(3, 'Almacén Tres'), credito: { limite: '10000.00', politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null } }
      x.clientes = [fuera, propio]
    })
    const datos = datosParaVenderDesde(b, [
      {
        operation_id: 'o',
        jornada_id: b.sesion.jornada.id,
        tipo: 'VENTA_DEBITO',
        producto_id: null,
        cliente_id: ID(103),
        cantidad_base: null,
        importe: '2000.00',
        estado_operacion: 'PENDIENTE',
      },
    ])

    const filas = clientesParaElegir(datos, '')

    expect(filas.map((f) => f.cliente.nombre)).toEqual(['Almacén Tres', 'Bazar Dos'])
    expect(filas[0]).toMatchObject({ saldoConsiderado: '3500.50', disponible: '6499.50' })
  })

  it('la búsqueda recorre a todos los clientes y el consumidor final no muestra saldo', () => {
    const b = bootstrapParaVender((x) => {
      x.clientes = [{ ...clienteDePrueba(1, 'Consumidor final'), es_consumidor_final: true }, { ...clienteDePrueba(2, 'Bazar Dos'), en_cartera: false }]
    })
    const datos = datosParaVenderDesde(b)

    expect(clientesParaElegir(datos, 'bazar').map((f) => f.cliente.nombre)).toEqual(['Bazar Dos'])
    expect(clientesParaElegir(datos, '')[0]).toMatchObject({ saldoConsiderado: null, disponible: null })
  })
})

describe('presentaciones de venta de un producto', () => {
  it('devuelve las presentaciones del producto con su referencia', () => {
    const datos = datosParaVenderDesde(bootstrapParaVender())

    expect(presentacionesDeVenta(datos, IDS.producto).map((p) => [p.nombre, p.unidadesBase, p.esReferencia])).toEqual([
      ['Unidad', 1, false],
      ['Caja x6', 6, true],
    ])
  })
})

