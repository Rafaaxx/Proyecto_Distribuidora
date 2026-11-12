import { baseLocal } from '../lib/dispositivo/db'

/**
 * Versión mínima de la aplicación (change 22b, `design.md` D7; `02` §6.6). El servidor informa
 * `app_version_minima` en `GET /api/v1/version` y no distingue una venta vieja encolada de una
 * nueva, así que el bloqueo es del teléfono: por debajo de la mínima la cola se sigue enviando
 * pero no se confirman ventas nuevas. La última mínima conocida vive en `meta` para que el
 * bloqueo siga sin señal. Si alguna de las dos versiones no tiene formato `X.Y.Z` (por ejemplo
 * `dev`) o la mínima es nula, no hay restricción.
 */
export const CLAVE_VERSION_MINIMA = 'app_version_minima'

const FORMATO = /^(\d+)\.(\d+)\.(\d+)$/

function partes(version: string): [number, number, number] | null {
  const coincidencia = FORMATO.exec(version)
  if (coincidencia === null) return null
  return [Number(coincidencia[1]), Number(coincidencia[2]), Number(coincidencia[3])]
}

/** Compara dos versiones `X.Y.Z` por números: negativo si `a < b`, 0 si iguales, positivo si `a > b`. */
export function compararVersiones(a: string, b: string): number {
  const pa = partes(a)
  const pb = partes(b)
  if (pa === null || pb === null) throw new Error('Versión sin formato X.Y.Z.')
  for (let i = 0; i < 3; i += 1) {
    const diferencia = (pa[i] as number) - (pb[i] as number)
    if (diferencia !== 0) return diferencia
  }
  return 0
}

export function estaPorDebajoDeLaMinima(propia: string, minima: string | null): boolean {
  if (minima === null || partes(propia) === null || partes(minima) === null) return false
  return compararVersiones(propia, minima) < 0
}

/** Pide la versión mínima al servidor y la guarda; sin señal o con error queda la última conocida. */
export async function actualizarVersionMinima(): Promise<void> {
  try {
    const señal = typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(8000) : undefined
    const respuesta = await fetch('/api/v1/version', { signal: señal })
    if (!respuesta.ok) return
    const cuerpo = (await respuesta.json()) as { app_version_minima?: string | null }
    const minima = cuerpo.app_version_minima ?? null
    if (minima === null) await baseLocal.meta.delete(CLAVE_VERSION_MINIMA)
    else await baseLocal.meta.put({ clave: CLAVE_VERSION_MINIMA, valor: minima })
  } catch {
    // Sin señal o respuesta ilegible: vale la última conocida y la cola se envía igual.
  }
}

export async function versionMinimaConocida(): Promise<string | null> {
  return (await baseLocal.meta.get(CLAVE_VERSION_MINIMA))?.valor ?? null
}

/** `true` si la aplicación está por debajo de la última mínima conocida: no se venden ventas nuevas. */
export async function ventaBloqueadaPorVersion(versionPropia: string): Promise<boolean> {
  return estaPorDebajoDeLaMinima(versionPropia, await versionMinimaConocida())
}

export const AVISO_DE_VERSION_MINIMA = 'Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación'
