import { baseLocal } from '../lib/dispositivo/db'

/**
 * Rechazos que administracion ya resolvio (change 25, `design.md` D8; SYN-09, CRE-08, INV-01).
 * El bootstrap informa los `operation_id` de los rechazos resueltos de su jornada, usuario y
 * dispositivo; el telefono los guarda en `meta` (sin version nueva de Dexie) dentro de la
 * transaccion de `aplicarBootstrap`, de modo que valen sin senal y despues de recargar.
 * Una operacion rechazada cuyo id esta aqui deja de contar en lo local y muestra «Resuelta por
 * administracion»; nunca se borra ni se reenvia.
 */
export const CLAVE_RECHAZOS_RESUELTOS = 'rechazos_resueltos'

/** Lo que se guarda en `meta`: el arreglo de ids como JSON (`valor` es siempre string). */
export function serializarRechazosResueltos(ids: readonly string[] | undefined): string {
  return JSON.stringify([...new Set(ids ?? [])])
}

function interpretar(valor: string | undefined): Set<string> {
  if (valor === undefined) return new Set()
  try {
    const dato: unknown = JSON.parse(valor)
    return Array.isArray(dato) ? new Set(dato.filter((x): x is string => typeof x === 'string')) : new Set()
  } catch {
    return new Set()
  }
}

/** Los `operation_id` resueltos del ultimo bootstrap; vacio si nunca llegaron. */
export async function leerRechazosResueltos(): Promise<Set<string>> {
  return interpretar((await baseLocal.meta.get(CLAVE_RECHAZOS_RESUELTOS))?.valor)
}
