import { liveQuery } from 'dexie'
import { useEffect, useState } from 'react'

import {
  filtrarYOrdenarClientes,
  precioDePresentacion,
  stockEnCajasYUnidades,
  versionVigente,
} from '../../../domain/ruta/lecturasLocales'
import {
  baseLocal,
  type ClienteLocal,
  type PresentacionLocal,
  type ProductoLocal,
  type SesionLocal,
} from '../../../lib/dispositivo/db'

/**
 * Hooks de lectura de la base local del área `/ruta` (change 21, tarea 7.2; spec
 * `sync/base-local`, "Las pantallas de ruta leen siempre de la base local"). Cada uno observa
 * Dexie con `liveQuery` (la API oficial; evita sumar `dexie-react-hooks`) y devuelve
 * `cargando`, `sin_datos` (no hay bootstrap aplicado) o `listo` con la hora de los datos.
 */
export type Lectura<T> = { estado: 'cargando' } | { estado: 'sin_datos' } | ({ estado: 'listo' } & T)

async function fechaDeLosDatos(): Promise<string | null> {
  return (await baseLocal.meta.get('fecha_bootstrap'))?.valor ?? null
}

/** Suscribe una consulta de Dexie; vuelve a evaluarla cuando cambian las tablas que lee. */
export function useConsultaLocal<T>(
  consulta: () => Promise<Lectura<T>>,
  claves: readonly (string | number)[],
): Lectura<T> {
  const [lectura, setLectura] = useState<Lectura<T>>({ estado: 'cargando' })
  const clave = JSON.stringify(claves)

  // La consulta se rehace solo cuando cambian sus claves (parámetros de la pantalla).
  useEffect(() => {
    const suscripcion = liveQuery(consulta).subscribe({
      next: setLectura,
      error: () => setLectura({ estado: 'sin_datos' }),
    })
    return () => suscripcion.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave])

  return lectura
}

export interface DatosDeInicio {
  usuario: SesionLocal['usuario']
  jornada: SesionLocal['jornada']
  /** Permisos del usuario al momento del bootstrap (ofrecer o no abrir la jornada). */
  permisos: string[]
  fechaBootstrap: string
}

export function useDatosDeInicio(): Lectura<DatosDeInicio> {
  return useConsultaLocal<DatosDeInicio>(async () => {
    const [fecha, sesion] = await Promise.all([fechaDeLosDatos(), baseLocal.sesion.get('actual')])
    if (fecha === null || sesion === undefined) return { estado: 'sin_datos' }
    return { estado: 'listo', usuario: sesion.usuario, jornada: sesion.jornada,
      permisos: sesion.permisos,
      fechaBootstrap: fecha,
    }
  }, [])
}

export function useClientesLocales(
  busqueda: string,
): Lectura<DatosDeClientes> {
  return useConsultaLocal<DatosDeClientes>(async () => {
    const fecha = await fechaDeLosDatos()
    if (fecha === null) return { estado: 'sin_datos' }
    const todos = await baseLocal.clientes.toArray()
    return { estado: 'listo', clientes: filtrarYOrdenarClientes(todos, busqueda), fechaBootstrap: fecha }
  }, [busqueda])
}

export interface DatosDeCliente {
  /** `null` si el cliente no está en la base local. */
  cliente: ClienteLocal | null
  /** Lista aplicable: la asignada al cliente o, si no tiene, la predeterminada. */
  listaNombre: string | null
  fechaBootstrap: string
}

export function useClienteLocal(id: string): Lectura<DatosDeCliente> {
  return useConsultaLocal<DatosDeCliente>(async () => {
    const fecha = await fechaDeLosDatos()
    if (fecha === null) return { estado: 'sin_datos' }
    const cliente = (await baseLocal.clientes.get(id)) ?? null
    const listas = await baseLocal.listas.toArray()
    const lista =
      listas.find((l) => l.id === cliente?.lista_precio_id) ?? listas.find((l) => l.es_predeterminada) ?? null
    return { estado: 'listo', cliente, listaNombre: lista?.nombre ?? null, fechaBootstrap: fecha }
  }, [id])
}

export interface PresentacionConPrecio {
  id: string
  nombre: string
  unidades_base: number
  /** Precio de la versión vigente en el momento pedido; `null` = "sin precio". */
  precio: string | null
}

export interface ProductoConPrecios {
  id: string
  codigo: string
  nombre: string
  presentaciones: PresentacionConPrecio[]
}

function coincideProducto(producto: ProductoLocal, busqueda: string): boolean {
  const q = busqueda.trim().toLowerCase()
  return producto.nombre.toLowerCase().includes(q) || producto.codigo.toLowerCase().includes(q)
}

/**
 * Productos con el precio de cada presentación según la versión vigente en `ahora` de la lista
 * predeterminada (D19; PRC-20, PRC-22). Las presentaciones van de menos unidades a más.
 */
export function useProductosLocales(
  busqueda: string,
  ahora: Date,
): Lectura<DatosDeProductos> {
  const instante = ahora.getTime()
  return useConsultaLocal<DatosDeProductos>(async () => {
    const fecha = await fechaDeLosDatos()
    if (fecha === null) return { estado: 'sin_datos' }

    const predeterminada = (await baseLocal.listas.toArray()).find((l) => l.es_predeterminada)
    const versiones = predeterminada
      ? await baseLocal.versiones.where('lista_id').equals(predeterminada.id).toArray()
      : []
    const vigente = versionVigente(versiones, new Date(instante))
    const precios = vigente ? await baseLocal.precios.where('version_id').equals(vigente.id).toArray() : []
    const precioDe = new Map(precios.map((p) => [p.producto_id, p]))

    const productos = (await baseLocal.productos.toArray())
      .filter((p) => busqueda.trim() === '' || coincideProducto(p, busqueda))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }))
    const porProducto = new Map<string, PresentacionLocal[]>()
    for (const p of await baseLocal.presentaciones.toArray()) {
      porProducto.set(p.producto_id, [...(porProducto.get(p.producto_id) ?? []), p])
    }

    return {
      estado: 'listo',
      fechaBootstrap: fecha,
      productos: productos.map((p) => ({
        id: p.id,
        codigo: p.codigo,
        nombre: p.nombre,
        presentaciones: (porProducto.get(p.id) ?? [])
          .sort((a, b) => a.unidades_base - b.unidades_base)
          .map((pr) => ({
            id: pr.id,
            nombre: pr.nombre,
            unidades_base: pr.unidades_base,
            precio: precioDePresentacion(precioDe.get(p.id), pr.unidades_base),
          })),
      })),
    }
  }, [busqueda, instante])
}

export interface FilaDeStock {
  producto_id: string
  nombre: string
  cantidad_base: number
  cajas: number
  unidades: number
}

/** Stock de la ubicación tomada, en cajas (presentación de referencia) y unidades (INV-04). */
export function useStockLocal(): Lectura<DatosDeStock> {
  return useConsultaLocal<DatosDeStock>(async () => {
    const fecha = await fechaDeLosDatos()
    if (fecha === null) return { estado: 'sin_datos' }

    const [stock, productos, presentaciones] = await Promise.all([
      baseLocal.stock.toArray(),
      baseLocal.productos.toArray(),
      baseLocal.presentaciones.toArray(),
    ])
    const productoPorId = new Map(productos.map((p) => [p.id, p]))
    const unidadesPorCaja = new Map(
      presentaciones.filter((p) => p.es_referencia).map((p) => [p.producto_id, p.unidades_base]),
    )

    const filas: FilaDeStock[] = stock.flatMap((s) => {
      const producto = productoPorId.get(s.producto_id)
      if (producto === undefined) return []
      const { cajas, unidades } = stockEnCajasYUnidades(
        s.cantidad_base,
        unidadesPorCaja.get(s.producto_id) ?? 1,
      )
      return [
        { producto_id: s.producto_id, nombre: producto.nombre, cantidad_base: s.cantidad_base, cajas, unidades },
      ]
    })
    filas.sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }))

    return { estado: 'listo', filas, fechaBootstrap: fecha }
  }, [])
}

export interface DatosDeClientes {
  clientes: ClienteLocal[]
  fechaBootstrap: string
}

export interface DatosDeProductos {
  productos: ProductoConPrecios[]
  fechaBootstrap: string
}

export interface DatosDeStock {
  filas: FilaDeStock[]
  fechaBootstrap: string
}
