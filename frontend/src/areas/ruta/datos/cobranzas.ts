import { liveQuery } from 'dexie'
import { useEffect, useState } from 'react'

import { baseLocal, type CobranzaLocal } from '../../../lib/dispositivo/db'
import { cobranzasDeLaJornada } from './sincronizacion'
import { useConsultaLocal, type Lectura } from './lecturas'

/**
 * Lecturas de las cobranzas del teléfono (change 23, `design.md` D8; SYN-09, COB-04). Todo sale de
 * Dexie, con o sin conexión, y se refresca solo cuando cambian las tablas. Solo las cobranzas
 * independientes: el cobro de una venta se ve con su venta.
 */
export interface DatosDeCobranzasDeHoy {
  cobranzas: CobranzaLocal[]
}

/** Las cobranzas de la jornada de la sesión, la más nueva primero. */
export function useCobranzasDeHoy(): Lectura<DatosDeCobranzasDeHoy> {
  return useConsultaLocal<DatosDeCobranzasDeHoy>(async () => {
    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) return { estado: 'sin_datos' }
    const cobranzas = await cobranzasDeLaJornada()
    cobranzas.sort((a, b) => (b.occurred_at ?? '').localeCompare(a.occurred_at ?? ''))
    return { estado: 'listo', cobranzas }
  }, [])
}

export type LecturaDeCobranza =
  | { estado: 'cargando' }
  | { estado: 'no_encontrada' }
  | { estado: 'lista'; cobranza: CobranzaLocal }

/** Una cobranza independiente por su identificador; el cobro de una venta no cuenta. */
export function useCobranzaLocal(cobranzaId: string): LecturaDeCobranza {
  const [lectura, setLectura] = useState<LecturaDeCobranza>({ estado: 'cargando' })
  useEffect(() => {
    const suscripcion = liveQuery(() => baseLocal.cobranzas.get(cobranzaId)).subscribe({
      next: (cobranza) =>
        setLectura(
          cobranza === undefined || cobranza.origen !== 'INDEPENDIENTE'
            ? { estado: 'no_encontrada' }
            : { estado: 'lista', cobranza },
        ),
      error: () => setLectura({ estado: 'no_encontrada' }),
    })
    return () => suscripcion.unsubscribe()
  }, [cobranzaId])
  return lectura
}
