import { saldoConsiderado, stockDisponible } from '../../../domain/ruta/disponiblesLocales'
import { baseLocal } from '../../../lib/dispositivo/db'

/**
 * Lectura de Dexie de los disponibles locales (change 22a, D5; CRE-08, RUT-04): lee la jornada
 * de la sesión, el valor del bootstrap y los movimientos, y delega la suma en funciones puras.
 */
export async function leerSaldoConsiderado(clienteId: string): Promise<string | null> {
  const sesion = await baseLocal.sesion.get('actual')
  const cliente = await baseLocal.clientes.get(clienteId)
  if (sesion === undefined || cliente === undefined) return null
  const movimientos = await baseLocal.movimientos_locales
    .where('[jornada_id+cliente_id]')
    .equals([sesion.jornada.id, clienteId])
    .toArray()
  return saldoConsiderado(cliente.saldo, movimientos, clienteId, sesion.jornada.id)
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
  return stockDisponible(fila?.cantidad_base ?? 0, movimientos, productoId, sesion.jornada.id)
}
