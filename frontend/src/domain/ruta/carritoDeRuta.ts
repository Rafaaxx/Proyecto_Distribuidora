import { admiteCajas, cantidadInicialDeProducto, type PresentacionDeVenta } from '../ventas/composicion'
import { MENSAJE_SIN_PRECIO } from '../ventas/pedido'
import { creditoDisponibleLocal, saldoConsiderado } from './disponiblesLocales'
import { filtrarYOrdenarClientes, precioDePresentacion } from './lecturasLocales'
import { puedeAgregarProducto } from './reglasDeVentaLocal'
import type { ClienteLocal } from '../../lib/dispositivo/db'
import type { CarritoDeRuta, DatosParaVender } from './armadoDeVentaLocal'

/**
 * El carrito de la venta de `/ruta` y el buscador de productos (change 22a, `design.md` D12,
 * D14; VTA-02, VTA-07, VTA-10, CAT-07, CAT-08, INV-04, PRC-22). Funciones puras: el carrito vive
 * solo en memoria (nunca se persiste) y los identificadores se piden a quien llama, así los
 * reintentos de confirmación reutilizan los mismos (INV-06).
 */
type NuevoId = () => string

export function carritoNuevo(clienteId: string, nuevoId: NuevoId): CarritoDeRuta {
  return {
    ventaId: nuevoId(),
    cobranzaId: nuevoId(),
    operationId: nuevoId(),
    clienteId,
    listaId: '',
    versionId: '',
    motivoListaId: '',
    items: [],
    generalTexto: '',
    propios: {},
    motivoDescuentoId: '',
    medios: [],
    observacionCobranza: '',
    aceptaExceso: false,
    seleccion: {},
    venderIgual: false,
  }
}

export function hayLineas(carrito: CarritoDeRuta): boolean {
  return carrito.items.length > 0
}

export interface ProductoParaAgregar {
  productoId: string
  presentaciones: readonly PresentacionDeVenta[]
}

/** Una caja si el producto se vende por caja; si no, una unidad (CAT-07). Una sola vez por producto. */
export function agregarProducto(carrito: CarritoDeRuta, producto: ProductoParaAgregar, nuevoId: NuevoId): CarritoDeRuta {
  if (carrito.items.some((i) => i.productoId === producto.productoId)) return carrito
  const inicial = cantidadInicialDeProducto(producto.presentaciones)
  const idsDeLinea = Object.fromEntries(producto.presentaciones.map((p) => [p.presentacionId, nuevoId()]))
  return {
    ...carrito,
    items: [...carrito.items, { productoId: producto.productoId, ...inicial, idsDeLinea }],
  }
}

export function cambiarCantidades(
  carrito: CarritoDeRuta,
  productoId: string,
  cambio: { cajas?: number; unidades?: number },
): CarritoDeRuta {
  return { ...carrito, items: carrito.items.map((i) => (i.productoId === productoId ? { ...i, ...cambio } : i)) }
}

export function quitarProducto(carrito: CarritoDeRuta, productoId: string): CarritoDeRuta {
  return { ...carrito, items: carrito.items.filter((i) => i.productoId !== productoId) }
}

export function agregarMedio(carrito: CarritoDeRuta): CarritoDeRuta {
  return { ...carrito, medios: [...carrito.medios, { medioPagoId: '', importe: '', referencia: '' }] }
}

export function cambiarMedio(
  carrito: CarritoDeRuta,
  indice: number,
  cambio: Partial<CarritoDeRuta['medios'][number]>,
): CarritoDeRuta {
  return { ...carrito, medios: carrito.medios.map((m, i) => (i === indice ? { ...m, ...cambio } : m)) }
}

export function quitarMedio(carrito: CarritoDeRuta, indice: number): CarritoDeRuta {
  return { ...carrito, medios: carrito.medios.filter((_, i) => i !== indice) }
}

/** Cantidad escrita como entero no negativo (INV-04); lo que no lo es cuenta como cero. */
export function leerCantidad(texto: string): number {
  const recortado = texto.trim()
  return /^\d+$/.test(recortado) ? Number.parseInt(recortado, 10) : 0
}

export interface PresentacionOfrecida {
  id: string
  nombre: string
  unidades_base: number
  es_referencia: boolean
  /** Precio de la presentación en la versión de la venta (PRC-22); nulo = sin precio. */
  precio: string | null
}

export interface ProductoOfrecido {
  id: string
  codigo: string
  nombre: string
  presentaciones: PresentacionOfrecida[]
  conPrecio: boolean
  /** "Producto sin precio en la lista: no se puede vender." (VTA-10). */
  mensaje: string | null
  vendePorCaja: boolean
}

function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

/** Los productos que coinciden con la búsqueda, con el precio de cada presentación en `versionId`. */
export function productosOfrecidos(datos: DatosParaVender, versionId: string, busqueda: string): ProductoOfrecido[] {
  const q = normalizar(busqueda.trim())
  const precioPorProducto = new Map(datos.precios.filter((p) => p.version_id === versionId).map((p) => [p.producto_id, p]))
  return datos.productos
    .filter((p) => q === '' || normalizar(p.nombre).includes(q) || normalizar(p.codigo).includes(q))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }))
    .map((producto) => {
      const precio = precioPorProducto.get(producto.id)
      const presentaciones = datos.presentaciones
        .filter((pr) => pr.producto_id === producto.id)
        .sort((a, b) => a.unidades_base - b.unidades_base)
      const agregable = puedeAgregarProducto(precio?.precio_referencia ?? null)
      return {
        id: producto.id,
        codigo: producto.codigo,
        nombre: producto.nombre,
        presentaciones: presentaciones.map((pr) => ({
          id: pr.id,
          nombre: pr.nombre,
          unidades_base: pr.unidades_base,
          es_referencia: pr.es_referencia,
          precio: precioDePresentacion(precio, pr.unidades_base),
        })),
        conPrecio: agregable.agregable,
        mensaje: agregable.agregable ? null : MENSAJE_SIN_PRECIO,
        vendePorCaja: admiteCajas(
          presentaciones.map((pr) => ({ presentacionId: pr.id, nombre: pr.nombre, unidadesBase: pr.unidades_base, esReferencia: pr.es_referencia })),
        ),
      }
    })
}

/** Las presentaciones de venta de un producto, de menos a más unidades base. */
export function presentacionesDeVenta(datos: DatosParaVender, productoId: string): PresentacionDeVenta[] {
  return datos.presentaciones
    .filter((p) => p.producto_id === productoId)
    .sort((a, b) => a.unidades_base - b.unidades_base)
    .map((p) => ({ presentacionId: p.id, nombre: p.nombre, unidadesBase: p.unidades_base, esReferencia: p.es_referencia }))
}

export interface ClienteParaElegir {
  cliente: ClienteLocal
  /** Nulo para el consumidor final (no tiene cuenta corriente). */
  saldoConsiderado: string | null
  /** Límite - saldo considerado; nulo sin límite o para el consumidor final. */
  disponible: string | null
}

/** Cartera primero, búsqueda en todos (CLI-02), con el saldo y el crédito que suman las ventas locales (CRE-08). */
export function clientesParaElegir(datos: DatosParaVender, busqueda: string): ClienteParaElegir[] {
  const jornadaId = datos.sesion.jornada.id
  return filtrarYOrdenarClientes(datos.clientes, busqueda).map((cliente) => {
    if (cliente.es_consumidor_final) return { cliente, saldoConsiderado: null, disponible: null }
    const saldo = saldoConsiderado(cliente.saldo, datos.movimientos, cliente.id, jornadaId)
    return { cliente, saldoConsiderado: saldo, disponible: creditoDisponibleLocal(cliente.credito.limite, saldo) }
  })
}
