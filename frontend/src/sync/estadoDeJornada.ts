import { apiFetch } from '../lib/api/httpClient'
import { baseLocal } from '../lib/dispositivo/db'

/**
 * Estado de la jornada de la sesión en el teléfono (change 22d, `design.md` D8; RUT-03, RUT-09,
 * SYN-07, SYN-09, INV-06, `02` §13.3). El teléfono se entera de que su jornada ya no está abierta
 * y lo guarda en `meta.jornada_no_abierta` (jornada, estado y momento), de modo que vale sin señal
 * y después de recargar. Lo corta «Vender» y «Anular venta» (Lote 3); lo ya vendido se sigue
 * enviando.
 *
 * Se aprende de cuatro maneras: la consulta de cada ciclo de sincronización, `JORNADA_REQUERIDA`
 * de «Actualizar datos» o del bootstrap, la consulta al entrar sin jornada abierta y una
 * `JORNADA_LIBERADA` en los resultados del lote. Sin señal, con 403, 404 o cualquier error, no
 * cambia nada. Una jornada `ABIERTA` tampoco cambia nada. Se borra al aplicar el bootstrap de otra
 * jornada (`aplicarBootstrap`). Un valor de otra jornada que la de la sesión se ignora.
 */
export const CLAVE_JORNADA_NO_ABIERTA = 'jornada_no_abierta'

/**
 * `ENTREGADA` (change 24, D10; RUT-05) es un estado LOCAL: el vendedor tocó «Terminar el día» y la
 * entrega espera su turno en la cola. Nunca lo informa el servidor; el estado que sí informa (por
 * ejemplo `EN_RENDICION`) lo reemplaza.
 */
export type EstadoDeJornadaNoAbierta = 'LIBERADA' | 'EN_RENDICION' | 'CERRADA' | 'ENTREGADA' | 'DESCONOCIDO'

export interface JornadaNoAbierta {
  jornada_id: string
  estado: EstadoDeJornadaNoAbierta
  /** Momento local (ISO) en que se aprendió. */
  en: string
}

/** Los estados que informa el servidor. */
const ESTADOS_CONOCIDOS: ReadonlySet<string> = new Set(['LIBERADA', 'EN_RENDICION', 'CERRADA'])
/** Lo que se acepta leer de `meta`: los del servidor y el local `ENTREGADA`. */
const ESTADOS_GUARDABLES: ReadonlySet<string> = new Set([...ESTADOS_CONOCIDOS, 'ENTREGADA'])

function interpretar(valor: string | undefined): JornadaNoAbierta | null {
  if (valor === undefined) return null
  try {
    const dato = JSON.parse(valor) as Partial<JornadaNoAbierta>
    if (typeof dato.jornada_id !== 'string' || typeof dato.en !== 'string') return null
    if (dato.estado !== 'DESCONOCIDO' && !ESTADOS_GUARDABLES.has(dato.estado ?? '')) return null
    return { jornada_id: dato.jornada_id, estado: dato.estado as EstadoDeJornadaNoAbierta, en: dato.en }
  } catch {
    return null
  }
}

/** Lo guardado, si es de la jornada de la sesión; si no, `null` («abierta» o sin dato). */
export async function leerJornadaNoAbierta(): Promise<JornadaNoAbierta | null> {
  const [sesion, fila] = await Promise.all([baseLocal.sesion.get('actual'), baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA)])
  const dato = interpretar(fila?.valor)
  if (sesion === undefined || dato === null || dato.jornada_id !== sesion.jornada.id) return null
  return dato
}

/**
 * Guarda que la jornada ya no está abierta. Solo si es la de la sesión local. Idempotente: el
 * mismo estado otra vez no cambia nada (ni el momento), y «desconocido» no pisa un estado conocido.
 */
export async function marcarJornadaNoAbierta(
  jornadaId: string,
  estado: EstadoDeJornadaNoAbierta,
  ahora: Date,
): Promise<void> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined || sesion.jornada.id !== jornadaId) return
  const actual = interpretar((await baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA))?.valor)
  if (actual !== null && actual.jornada_id === jornadaId) {
    if (actual.estado === estado) return
    if (estado === 'DESCONOCIDO') return
  }
  const nuevo: JornadaNoAbierta = { jornada_id: jornadaId, estado, en: ahora.toISOString() }
  await baseLocal.meta.put({ clave: CLAVE_JORNADA_NO_ABIERTA, valor: JSON.stringify(nuevo) })
}

/**
 * Al aplicar un bootstrap: si lo guardado es de otra jornada que la del bootstrap, se borra (el
 * vendedor abrió una jornada nueva). Solo lee y escribe `meta`, así que cabe en su transacción.
 */
export async function borrarMarcaSiEsDeOtraJornada(jornadaIdDelBootstrap: string): Promise<void> {
  const actual = interpretar((await baseLocal.meta.get(CLAVE_JORNADA_NO_ABIERTA))?.valor)
  if (actual === null || actual.jornada_id !== jornadaIdDelBootstrap) {
    await baseLocal.meta.delete(CLAVE_JORNADA_NO_ABIERTA)
  }
}

/** Marca la jornada de la sesión local como no abierta, sin estado conocido (`JORNADA_REQUERIDA`). */
export async function marcarJornadaDeLaSesionNoAbierta(
  estado: EstadoDeJornadaNoAbierta,
  ahora: Date,
): Promise<void> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion !== undefined) await marcarJornadaNoAbierta(sesion.jornada.id, estado, ahora)
}

/**
 * Al empezar cada ciclo de sincronización: `GET /api/v1/stock/jornadas/{id}` de la sesión. Si la
 * jornada no está `ABIERTA` guarda su estado. Cualquier falla (sin señal, 403 sin `ABRIR_JORNADA`,
 * 404, error del servidor, respuesta ilegible) deja todo como estaba: la cola se envía igual.
 */
export async function consultarEstadoDeJornada(ahora: Date): Promise<void> {
  try {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return
    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) return
    const respuesta = await apiFetch(`/stock/jornadas/${sesion.jornada.id}`)
    if (!respuesta.ok) return
    const { estado } = (await respuesta.json()) as { estado?: string }
    if (estado !== undefined && ESTADOS_CONOCIDOS.has(estado)) {
      await marcarJornadaNoAbierta(sesion.jornada.id, estado as EstadoDeJornadaNoAbierta, ahora)
    }
  } catch {
    // Sin señal o respuesta ilegible: vale lo último que se supo.
  }
}
