import { baseLocal, TABLAS_MAESTRAS } from '../dispositivo/db'
import { CLAVES_DE_PIN } from './pin'

/**
 * Sesión local del dispositivo (change 21, `design.md` D16; `02` §12.3): una sola a la vez.
 * `meta.usuario_local_id` dice a quién pertenecen los datos del teléfono. Borrar la sesión local
 * quita el usuario, el PIN y los datos maestros; NUNCA toca `meta.dispositivo_id` ni las
 * operaciones pendientes (SYN-09): la lista de claves de `meta` es explícita.
 */
const CLAVE_USUARIO_LOCAL = 'usuario_local_id'

/** Claves de `meta` que pertenecen a la sesión y a su bootstrap (el resto de `meta` no se toca). */
const CLAVES_DE_SESION = [CLAVE_USUARIO_LOCAL, 'fecha_bootstrap', 'jornada_id', ...CLAVES_DE_PIN]

export async function usuarioLocalId(): Promise<string | undefined> {
  return (await baseLocal.meta.get(CLAVE_USUARIO_LOCAL))?.valor
}

export async function fijarUsuarioLocal(usuarioId: string): Promise<void> {
  await baseLocal.meta.put({ clave: CLAVE_USUARIO_LOCAL, valor: usuarioId })
}

/** Borra usuario, PIN y datos maestros en una sola transacción. */
export async function borrarSesionLocal(): Promise<void> {
  const tablas = [...TABLAS_MAESTRAS.map((nombre) => baseLocal.table(nombre)), baseLocal.meta]
  await baseLocal.transaction('rw', tablas, async () => {
    await Promise.all(TABLAS_MAESTRAS.map((nombre) => baseLocal.table(nombre).clear()))
    await baseLocal.meta.bulkDelete(CLAVES_DE_SESION)
  })
}
