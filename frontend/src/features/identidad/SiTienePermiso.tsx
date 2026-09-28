import type { ReactNode } from 'react'

import type { CodigoPermiso } from '../../domain/identidad/permisos'
import { usePermisos } from './usePermisos'

export interface SiTienePermisoProps {
  permiso: CodigoPermiso
  /** Se muestra sin el permiso. Sin este prop, no se muestra nada
   * (tarea 6.4). */
  fallback?: ReactNode
  /** Se muestra mientras `usePermisos()` está pendiente. Sin este prop,
   * no se muestra nada mientras carga. */
  cargando?: ReactNode
  children: ReactNode
}

/**
 * Único mecanismo compartido para mostrar u ocultar según un permiso
 * (tarea 6.4, `design.md` D3-A / D4-A, ADR-027 "solo este mecanismo").
 *
 * Sin el permiso, los hijos **no se montan**: React nunca evalúa
 * `children` en esa rama, así que un componente que carga datos dentro
 * de `<SiTienePermiso>` nunca dispara su consulta (fallo cerrado,
 * D4-A -- "las pantallas no piden un dato solo para averiguar si tiene
 * permiso"). Ocultar es una comodidad de la interfaz: el servidor sigue
 * validando cada petición (SEG-06).
 */
export function SiTienePermiso({ permiso, fallback = null, cargando = null, children }: SiTienePermisoProps) {
  const permisos = usePermisos()

  if (permisos.estado === 'cargando') {
    return <>{cargando}</>
  }

  if (!permisos.tiene(permiso)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}
