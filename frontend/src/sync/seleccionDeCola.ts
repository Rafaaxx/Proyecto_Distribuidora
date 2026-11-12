import { baseLocal, type ComandoEnCola } from '../lib/dispositivo/db'

/**
 * Qué parte de la cola se envía (change 22b, `design.md` D1; SYN-03, RUT-09, `02` §6.4): los
 * comandos `PENDIENTE` del usuario de la sesión local y de este teléfono, de cualquier jornada,
 * en orden de `secuencia`. Los de otro usuario no se tocan (ADR-063 D16): el servidor nunca
 * recibe un ítem ajeno. Un `RECHAZADO` no está pendiente: no se reenvía solo.
 */
export const TAMANO_DE_LOTE = 50

export async function seleccionarCola(usuarioId: string, dispositivoId: string): Promise<ComandoEnCola[]> {
  const pendientes = await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()
  return pendientes
    .filter((c) => c.sobre.usuario_id === usuarioId && c.sobre.dispositivo_id === dispositivoId)
    .sort((a, b) => a.secuencia - b.secuencia)
}

/** Parte la cola ya ordenada en lotes de hasta `TAMANO_DE_LOTE` (máximo de `02` §6.4). */
export function partirEnLotes(cola: ComandoEnCola[]): ComandoEnCola[][] {
  const lotes: ComandoEnCola[][] = []
  for (let i = 0; i < cola.length; i += TAMANO_DE_LOTE) lotes.push(cola.slice(i, i + TAMANO_DE_LOTE))
  return lotes
}
