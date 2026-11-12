import { liveQuery } from 'dexie'
import { useEffect, useState } from 'react'

import { leerRechazosResueltos } from '../../../sync/rechazosResueltos'

const VACIO: ReadonlySet<string> = new Set()

/**
 * Los `operation_id` de los rechazos que administración resolvió (change 25, D8; SYN-09), leídos de
 * `meta` con o sin conexión y actualizados cuando el bootstrap los renueva. Sin lógica de negocio.
 */
export function useRechazosResueltos(): ReadonlySet<string> {
  const [ids, setIds] = useState<ReadonlySet<string>>(VACIO)
  useEffect(() => {
    const suscripcion = liveQuery(leerRechazosResueltos).subscribe({
      next: setIds,
      error: () => setIds(VACIO),
    })
    return () => suscripcion.unsubscribe()
  }, [])
  return ids
}
