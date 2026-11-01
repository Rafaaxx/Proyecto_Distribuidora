/**
 * `navigator.locks` de prueba con exclusión real compartida entre las «pestañas» del mismo proceso
 * (change 22b, tarea 1.1; `02` §13.3). Implementa lo que usa el código: `request(nombre, [opciones],
 * callback)` exclusivo, con `ifAvailable` (el callback recibe `null` si el candado está tomado).
 */
interface OpcionesDeCandado {
  ifAvailable?: boolean
}
type TareaDeCandado = (candado: object | null) => Promise<unknown> | unknown

export interface CandadosDePrueba {
  /** Nombres pedidos, en orden (sirve para comprobar qué candado se usó). */
  pedidos: string[]
  restaurar: () => void
}

export function instalarCandadosDePrueba(): CandadosDePrueba {
  const ocupacion = new Map<string, number>()
  const colas = new Map<string, Promise<unknown>>()
  const pedidos: string[] = []

  async function request(nombre: string, a: OpcionesDeCandado | TareaDeCandado, b?: TareaDeCandado): Promise<unknown> {
    const opciones = typeof a === 'function' ? {} : a
    const tarea = (typeof a === 'function' ? a : b) as TareaDeCandado
    pedidos.push(nombre)
    if (opciones.ifAvailable === true && (ocupacion.get(nombre) ?? 0) > 0) return tarea(null)

    ocupacion.set(nombre, (ocupacion.get(nombre) ?? 0) + 1)
    const ejecucion = (colas.get(nombre) ?? Promise.resolve()).then(() => tarea({}))
    colas.set(
      nombre,
      ejecucion.catch(() => undefined),
    )
    try {
      return await ejecucion
    } finally {
      ocupacion.set(nombre, (ocupacion.get(nombre) ?? 1) - 1)
    }
  }

  const original = Object.getOwnPropertyDescriptor(window.navigator, 'locks')
  Object.defineProperty(window.navigator, 'locks', { configurable: true, value: { request } })

  return {
    pedidos,
    restaurar: () => {
      if (original !== undefined) Object.defineProperty(window.navigator, 'locks', original)
      else Reflect.deleteProperty(window.navigator, 'locks')
    },
  }
}
