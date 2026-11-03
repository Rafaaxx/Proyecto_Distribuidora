import {
  saldoConsiderado,
  stockDeTodos,
  stockDisponible,
  type Conciliacion,
} from '../../../domain/ruta/disponiblesLocales'
import { baseLocal } from '../../../lib/dispositivo/db'

/**
 * Lectura de Dexie de los disponibles locales (change 22a, D5; change 22c, D1 y D2; CRE-08,
 * RUT-04): lee la jornada y la marca de la sesión, el valor del bootstrap, los movimientos y la
 * secuencia y el estado de cada operación de `cola`, y delega la suma en funciones puras.
 */
export async function leerConciliacion(): Promise<Conciliacion> {
  const sesion = await baseLocal.sesion.get('actual')
  const cola = await baseLocal.cola.toArray()
  return {
    secuenciaProcesada: sesion?.secuencia_procesada ?? null,
    operaciones: new Map(
      cola.map((c) => [c.operation_id, { secuencia: c.secuencia, rechazada: c.estado === 'RECHAZADO' }]),
    ),
  }
}

export async function leerSaldoConsiderado(clienteId: string): Promise<string | null> {
  const sesion = await baseLocal.sesion.get('actual')
  const cliente = await baseLocal.clientes.get(clienteId)
  if (sesion === undefined || cliente === undefined) return null
  const movimientos = await baseLocal.movimientos_locales
    .where('[jornada_id+cliente_id]')
    .equals([sesion.jornada.id, clienteId])
    .toArray()
  return saldoConsiderado(cliente.saldo, movimientos, clienteId, sesion.jornada.id, await leerConciliacion())
}

/** Disponible en unidad base; un producto sin fila de stock parte de cero. */
export async function leerStockDisponible(productoId: string): Promise<number> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) return 0
  const fila = await baseLocal.stock.get(productoId)
  const movimientos = await baseLocal.movimientos_locales
    .where('[jornada_id+producto_id]')
    .equals([sesion.jornada.id, productoId])
    .toArray()
  return stockDisponible(fila?.cantidad_base ?? 0, movimientos, productoId, sesion.jornada.id, await leerConciliacion())
}

/** Disponible de todos los productos (pantalla de Stock), por `producto_id`. */
export async function leerStockDeTodos(): Promise<Map<string, number>> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) return new Map()
  const [stock, movimientos, conciliacion] = await Promise.all([
    baseLocal.stock.toArray(),
    baseLocal.movimientos_locales.filter((m) => m.jornada_id === sesion.jornada.id).toArray(),
    leerConciliacion(),
  ])
  return stockDeTodos(stock, movimientos, sesion.jornada.id, conciliacion)
}
