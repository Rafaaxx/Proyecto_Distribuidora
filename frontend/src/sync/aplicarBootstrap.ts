import type { components } from '../api/schema.gen'
import {
  baseLocal,
  TABLAS_MAESTRAS,
  type CatalogoLocal,
  type ConfiguracionLocal,
  type ListaLocal,
  type PrecioLocal,
  type PresentacionLocal,
  type ProductoLocal,
  type SesionLocal,
  type VersionLocal,
} from '../lib/dispositivo/db'

/**
 * Aplica el bootstrap a la base local (change 21, `design.md` D10; ADR-006, INV-01,
 * `02` §13.4): UNA transacción `rw` que vacía y rellena la lista explícita de tablas maestras y
 * escribe `meta.fecha_bootstrap` y `meta.jornada_id`. Si algo falla, Dexie revierte todo y
 * queda el bootstrap anterior. No toca `meta.dispositivo_id` ni las tablas de operaciones.
 * Los importes quedan como string (INV-03) y las cantidades como enteros (INV-04).
 */
export type BootstrapRespuesta = components['schemas']['BootstrapResponse']

interface FilasLocales {
  sesion: SesionLocal
  configuracion: ConfiguracionLocal
  productos: ProductoLocal[]
  presentaciones: PresentacionLocal[]
  clientes: BootstrapRespuesta['clientes']
  listas: ListaLocal[]
  versiones: VersionLocal[]
  precios: PrecioLocal[]
  reglas: BootstrapRespuesta['reglas_descuento']
  stock: BootstrapRespuesta['stock']
  autorizadores: BootstrapRespuesta['autorizadores']
  catalogos: CatalogoLocal[]
}

/** Adaptador puro de la respuesta tipada a filas locales. */
export function adaptarBootstrap(b: BootstrapRespuesta): FilasLocales {
  const productos: ProductoLocal[] = []
  const presentaciones: PresentacionLocal[] = []
  for (const { presentaciones: dePresentaciones, ...producto } of b.productos) {
    productos.push(producto)
    for (const p of dePresentaciones) presentaciones.push({ ...p, producto_id: producto.id })
  }

  const listas: ListaLocal[] = []
  const versiones: VersionLocal[] = []
  const precios: PrecioLocal[] = []
  for (const lista of b.listas) {
    listas.push({ id: lista.id, nombre: lista.nombre, es_predeterminada: lista.es_predeterminada })
    for (const { precios: dePrecios, ...version } of lista.versiones) {
      versiones.push({ ...version, lista_id: lista.id })
      for (const precio of dePrecios) precios.push({ ...precio, version_id: version.id })
    }
  }

  return {
    sesion: {
      clave: 'actual',
      usuario: b.sesion.usuario,
      permisos: b.sesion.permisos,
      jornada: b.sesion.jornada,
      numeracion: b.sesion.numeracion,
      contexto_venta: b.contexto_venta,
    },
    configuracion: { clave: 'organizacion', ...b.configuracion },
    productos,
    presentaciones,
    clientes: b.clientes,
    listas,
    versiones,
    precios,
    reglas: b.reglas_descuento,
    stock: b.stock,
    autorizadores: b.autorizadores,
    catalogos: [
      { clave: 'medios_pago', items: b.catalogos.medios_pago },
      { clave: 'motivos', items: b.catalogos.motivos },
      { clave: 'alicuotas', items: b.catalogos.alicuotas },
    ],
  }
}

export async function aplicarBootstrap(respuesta: BootstrapRespuesta): Promise<void> {
  const filas = adaptarBootstrap(respuesta)
  const tablas = [...TABLAS_MAESTRAS.map((nombre) => baseLocal.table(nombre)), baseLocal.meta, baseLocal.intentos_pin]

  await baseLocal.transaction('rw', tablas, async () => {
    await Promise.all(TABLAS_MAESTRAS.map((nombre) => baseLocal.table(nombre).clear()))

    await baseLocal.sesion.put(filas.sesion)
    await baseLocal.configuracion.put(filas.configuracion)
    await baseLocal.productos.bulkPut(filas.productos)
    await baseLocal.presentaciones.bulkPut(filas.presentaciones)
    await baseLocal.clientes.bulkPut(filas.clientes)
    await baseLocal.listas.bulkPut(filas.listas)
    await baseLocal.versiones.bulkPut(filas.versiones)
    await baseLocal.precios.bulkPut(filas.precios)
    await baseLocal.reglas_descuento.bulkPut(filas.reglas)
    await baseLocal.stock.bulkPut(filas.stock)
    await baseLocal.autorizadores.bulkPut(filas.autorizadores)
    await baseLocal.catalogos.bulkPut(filas.catalogos)

    // Cualquier bootstrap nuevo levanta los bloqueos y reinicia las cuentas del PIN de supervisor
    // (D10 = B, ADR-055). Es la única tabla de operaciones que el bootstrap vacía.
    await baseLocal.intentos_pin.clear()

    await baseLocal.meta.put({ clave: 'fecha_bootstrap', valor: respuesta.generado_en })
    await baseLocal.meta.put({ clave: 'jornada_id', valor: respuesta.sesion.jornada.id })
  })
}
