import { useEffect, useState } from 'react'
import { liveQuery } from 'dexie'

import { baseLocal, type VentaLocal } from '../../../lib/dispositivo/db'
import { contarVentasSinEnviar } from '../../../sync/ventasPendientes'
import { useConsultaLocal, type Lectura } from './lecturas'

/**
 * Lecturas de las ventas del teléfono (change 22a, `design.md` D13, D14; SYN-09, RUT-04). Todo
 * sale de Dexie, con o sin conexión, y se refresca solo cuando cambian las tablas.
 */
export interface DatosDeVentasDeHoy {
  ventas: VentaLocal[]
}

/** Las ventas de la jornada de la sesión, la más nueva primero; las de otra jornada no aparecen. */
export function useVentasDeHoy(): Lectura<DatosDeVentasDeHoy> {
  return useConsultaLocal<DatosDeVentasDeHoy>(async () => {
    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) return { estado: 'sin_datos' }
    const ventas = await baseLocal.ventas.where('jornada_id').equals(sesion.jornada.id).toArray()
    ventas.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at) || b.numero.localeCompare(a.numero))
    return { estado: 'listo', ventas }
  }, [])
}

export type LecturaDeVenta = { estado: 'cargando' } | { estado: 'no_encontrada' } | { estado: 'lista'; venta: VentaLocal }

export function useVentaLocal(ventaId: string): LecturaDeVenta {
  const [lectura, setLectura] = useState<LecturaDeVenta>({ estado: 'cargando' })
  useEffect(() => {
    const suscripcion = liveQuery(() => baseLocal.ventas.get(ventaId)).subscribe({
      next: (venta) => setLectura(venta === undefined ? { estado: 'no_encontrada' } : { estado: 'lista', venta }),
      error: () => setLectura({ estado: 'no_encontrada' }),
    })
    return () => suscripcion.unsubscribe()
  }, [ventaId])
  return lectura
}

/** Cantidad de ventas sin enviar del usuario de la sesión; `null` mientras carga. */
export function useVentasSinEnviar(usuarioId: string | null): number | null {
  const [cantidad, setCantidad] = useState<number | null>(null)
  useEffect(() => {
    if (usuarioId === null) return undefined
    const suscripcion = liveQuery(() => contarVentasSinEnviar(usuarioId)).subscribe({
      next: setCantidad,
      error: () => setCantidad(null),
    })
    return () => suscripcion.unsubscribe()
  }, [usuarioId])
  return cantidad
}
