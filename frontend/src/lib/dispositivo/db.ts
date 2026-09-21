import Dexie, { type EntityTable } from 'dexie'

/**
 * Base local Dexie/IndexedDB (`docs/02-arquitectura.md` §13.2). Este change
 * (03) solo necesita la tabla `meta` para el identificador de dispositivo
 * (tarea 13.6); el resto de las tablas de esa sección (`sesion`,
 * `productos`, `cola`, etc.) llegan con los changes que implementan el
 * área `/ruta` y el bootstrap.
 */
export interface RegistroMeta {
  clave: string
  valor: string
}

class BaseLocal extends Dexie {
  meta!: EntityTable<RegistroMeta, 'clave'>

  constructor() {
    super('distribuidora')
    this.version(1).stores({
      meta: 'clave',
    })
  }
}

export const baseLocal = new BaseLocal()
