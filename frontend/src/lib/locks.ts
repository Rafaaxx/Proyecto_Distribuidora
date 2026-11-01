/**
 * Envoltura de Web Locks (change 22b, `design.md` D2; `02` §13.3). Con `navigator.locks` el candado
 * vale entre todas las pestañas del origen; sin él (navegador viejo) cae a un candado dentro de la
 * pestaña con la misma interfaz: dos pestañas podrían entrar a la vez, y es seguro porque el
 * servidor no duplica (INV-06).
 */
export type ResultadoDeCandado<T> = { obtenido: true; valor: T } | { obtenido: false }

function candadosDelNavegador(): LockManager | undefined {
  return typeof navigator === 'undefined' ? undefined : navigator.locks
}

// Alternativa de pestaña: cola por nombre y cuenta de quienes lo tienen o esperan.
const colasDePestana = new Map<string, Promise<unknown>>()
const ocupacionDePestana = new Map<string, number>()

async function conCandadoDePestana<T>(nombre: string, tarea: () => Promise<T>): Promise<T> {
  ocupacionDePestana.set(nombre, (ocupacionDePestana.get(nombre) ?? 0) + 1)
  const ejecucion = (colasDePestana.get(nombre) ?? Promise.resolve()).then(tarea)
  colasDePestana.set(
    nombre,
    ejecucion.catch(() => undefined),
  )
  try {
    return await ejecucion
  } finally {
    ocupacionDePestana.set(nombre, (ocupacionDePestana.get(nombre) ?? 1) - 1)
  }
}

/** Ejecuta `tarea` en exclusión con el candado `nombre`; espera su turno si está tomado. */
export async function conCandado<T>(nombre: string, tarea: () => Promise<T>): Promise<T> {
  const candados = candadosDelNavegador()
  if (candados === undefined) return conCandadoDePestana(nombre, tarea)
  return candados.request(nombre, tarea)
}

/** Como `conCandado`, pero si está tomado no espera ni ejecuta: informa `{ obtenido: false }`. */
export async function conCandadoSiLibre<T>(nombre: string, tarea: () => Promise<T>): Promise<ResultadoDeCandado<T>> {
  const candados = candadosDelNavegador()
  if (candados === undefined) {
    if ((ocupacionDePestana.get(nombre) ?? 0) > 0) return { obtenido: false }
    return { obtenido: true, valor: await conCandadoDePestana(nombre, tarea) }
  }
  return candados.request(nombre, { ifAvailable: true }, async (candado): Promise<ResultadoDeCandado<T>> => {
    if (candado === null) return { obtenido: false }
    return { obtenido: true, valor: await tarea() }
  })
}
