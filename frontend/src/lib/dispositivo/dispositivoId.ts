import { baseLocal } from './db'

/**
 * `docs/02-arquitectura.md` §12.2: "En el primer inicio, la aplicación
 * genera un `dispositivo_id` y lo guarda en IndexedDB. El login lo envía".
 * Tarea 13.6.
 */
const CLAVE_DISPOSITIVO_ID = 'dispositivo_id'

// Deduplica llamadas concurrentes durante el primer arranque: sin esto, dos
// llamadas simultáneas podrían ver ambas la tabla vacía y generar dos
// identificadores distintos antes de que la primera termine de escribir el
// suyo.
let generacionEnCurso: Promise<string> | null = null

export async function obtenerOGenerarDispositivoId(): Promise<string> {
  if (generacionEnCurso) {
    return generacionEnCurso
  }

  generacionEnCurso = (async () => {
    const existente = await baseLocal.meta.get(CLAVE_DISPOSITIVO_ID)
    if (existente) {
      return existente.valor
    }
    const nuevo = crypto.randomUUID()
    await baseLocal.meta.put({ clave: CLAVE_DISPOSITIVO_ID, valor: nuevo })
    return nuevo
  })()

  try {
    return await generacionEnCurso
  } finally {
    generacionEnCurso = null
  }
}
