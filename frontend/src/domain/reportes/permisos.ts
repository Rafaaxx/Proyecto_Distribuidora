import type { CodigoPermiso } from '../identidad/permisos'

/** Predicado de permiso de `usePermisos().tiene`. */
export type TienePermisoDeReportes = (permiso: CodigoPermiso) => boolean

/** Los permisos que, junto con `VER_REPORTES`, abren los saldos de proveedores (D8 = B). */
const PERMISOS_DE_PROVEEDORES: readonly CodigoPermiso[] = [
  'GESTIONAR_PROVEEDORES',
  'REGISTRAR_PAGO_PROVEEDOR',
  'VER_UTILIDAD',
]

/**
 * Regla compuesta de los saldos de proveedores (change 26, D8 = B; `01` §19; SEG-06): `VER_REPORTES` y además
 * alguno de `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `VER_UTILIDAD`. Es una comodidad de la
 * interfaz: el servidor aplica la misma regla en cada petición.
 */
export function veSaldosDeProveedores(tiene: TienePermisoDeReportes): boolean {
  return tiene('VER_REPORTES') && PERMISOS_DE_PROVEEDORES.some((permiso) => tiene(permiso))
}
