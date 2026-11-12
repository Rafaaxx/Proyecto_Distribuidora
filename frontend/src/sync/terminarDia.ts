import { siguienteSecuencia } from '../domain/ruta/numeracionLocal'
import { baseLocal, type ComandoEnCola } from '../lib/dispositivo/db'
import { CLAVE_ULTIMA_SECUENCIA } from './confirmarVentaLocal'
import { marcarJornadaNoAbierta } from './estadoDeJornada'
import { armarSobreDeEntrega } from './sobre'

/**
 * «Terminar el día» del vendedor (change 24, `design.md` D1, D10; **INV-01**, INV-06, RUT-05,
 * SYN-03, `02` §13.2).
 *
 * UNA transacción `rw` de Dexie sobre `sesion`, `meta` y `cola`: encola `JORNADA_ENTREGAR`
 * `OFFLINE` con la siguiente secuencia, avanza la última secuencia y guarda la marca `ENTREGADA`
 * de la jornada en `meta` (el mismo dato de ADR-066; sin versión nueva de Dexie). Si algo falla no
 * queda nada. Con o sin señal: el lote la envía detrás de todo lo anterior.
 *
 * Reconfirmar (doble toque, reintento) no encola otra entrega: devuelve la existente (`repetida`).
 */
export interface EntradaDeTerminarElDia {
  /** UUIDv7 de la entrega. */
  operationId: string
  usuarioId: string
  dispositivoId: string
  ahora: Date
  appVersion: string
}

export interface ResultadoDeTerminarElDia {
  comando: ComandoEnCola
  /** `true` si la jornada ya tenía su entrega encolada y no se escribió nada. */
  repetida: boolean
}

export const TIPO_DE_ENTREGA = 'JORNADA_ENTREGAR'

export async function terminarElDia(entrada: EntradaDeTerminarElDia): Promise<ResultadoDeTerminarElDia> {
  return baseLocal.transaction('rw', [baseLocal.sesion, baseLocal.meta, baseLocal.cola], async () => {
    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) throw new Error('No hay sesión local: no se puede terminar el día.')

    const existente = (await baseLocal.cola.toArray()).find(
      (c) => c.sobre.tipo === TIPO_DE_ENTREGA && c.sobre.jornada_id === sesion.jornada.id,
    )
    if (existente !== undefined) return { comando: existente, repetida: true }

    const ultimaSecuencia = (await baseLocal.meta.get(CLAVE_ULTIMA_SECUENCIA))?.valor
    const secuencia = siguienteSecuencia(ultimaSecuencia === undefined ? null : Number(ultimaSecuencia))
    const sobre = armarSobreDeEntrega({
      operationId: entrada.operationId,
      usuarioId: entrada.usuarioId,
      dispositivoId: entrada.dispositivoId,
      jornadaId: sesion.jornada.id,
      occurredAt: entrada.ahora,
      secuencia,
      appVersion: entrada.appVersion,
    })
    const comando: ComandoEnCola = { secuencia, operation_id: entrada.operationId, estado: 'PENDIENTE', sobre }

    await baseLocal.cola.add(comando)
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SECUENCIA, valor: String(secuencia) })
    await marcarJornadaNoAbierta(sesion.jornada.id, 'ENTREGADA', entrada.ahora)

    return { comando, repetida: false }
  })
}
