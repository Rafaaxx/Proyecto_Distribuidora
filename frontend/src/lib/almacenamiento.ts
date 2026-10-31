/**
 * Almacenamiento persistente del navegador (change 21, `design.md` D18; `02` §13.3, `00` §11).
 * Sin él, el navegador puede borrar la base local (Dexie) si le falta espacio. Se pide tras el
 * primer bootstrap y en cada arranque mientras no esté concedido. Chrome lo concede a una
 * aplicación instalada; Safari lo decide él y puede no ofrecer la API: en ese caso el inicio
 * muestra una advertencia permanente. Ninguna API es exclusiva de Android.
 */
export type EstadoDeAlmacenamiento = 'concedido' | 'negado' | 'no_disponible'

export async function asegurarAlmacenamientoPersistente(): Promise<EstadoDeAlmacenamiento> {
  const almacenamiento: Partial<StorageManager> | undefined = globalThis.navigator?.storage
  if (typeof almacenamiento?.persisted !== 'function' || typeof almacenamiento.persist !== 'function') {
    return 'no_disponible'
  }
  try {
    if (await almacenamiento.persisted()) return 'concedido'
    return (await almacenamiento.persist()) ? 'concedido' : 'negado'
  } catch {
    return 'negado'
  }
}
