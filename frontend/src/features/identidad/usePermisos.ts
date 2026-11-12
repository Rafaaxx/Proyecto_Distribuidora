import { useQuery } from '@tanstack/react-query'

import type { CodigoPermiso } from '../../domain/identidad/permisos'
import { ErrorDeIdentidad, obtenerYo, type Yo } from './api'
import { clavesIdentidad } from './claves'

export type EstadoDePermisos = 'cargando' | 'error' | 'listo'

export interface Permisos {
  estado: EstadoDePermisos
  /** Falla cerrada (`design.md` D3-A, B1): falso mientras la consulta está
   * pendiente y ante un error, nunca solo cuando el permiso realmente
   * falta. Ninguna pantalla puede confundir "todavía no sé" con "no
   * tiene". */
  tiene(permiso: CodigoPermiso): boolean
  yo: Yo | undefined
  /** Error de la consulta, solo cuando `/yo` respondió con un error HTTP
   * (`ErrorDeIdentidad`, con su `status`); un fallo de red no trae estado
   * y se informa `undefined`. Lo necesita el menú para distinguir "falló
   * la consulta" de "la sesión terminó" (`design.md` D3-A, tarea 7.4): con
   * un 401 tras una renovación rechazada no tiene sentido reintentar, se
   * ofrece iniciar sesión. */
  error: ErrorDeIdentidad | undefined
  reintentar(): void
}

/**
 * Única fuente de permisos de `/admin` (tarea 6.3, `design.md` D2-A):
 * envuelve `useQuery(['yo'])` con `staleTime: Infinity` y
 * `refetchOnWindowFocus: false` -- la consulta solo se repite por la
 * invalidación explícita de `AdminScreen` ante un cambio de token (tarea
 * 6.5), nunca por foco de ventana ni por "stale" automático (ADR-027: "un
 * pedido extra por sesión y por renovación").
 *
 * `retry: false` (tarea 11.2, **B1**): sin esto, un 401 de `/yo` queda
 * reintentándose con el backoff por defecto de TanStack Query (1 s + 2 s +
 * 4 s) y, como el aviso "Iniciar sesión" del encabezado solo existe en
 * estado `error`, el corte recién se ve después de 7 segundos, o no se ve
 * nunca si otro reintento vuelve a fallar mientras tanto. Reintentar es una
 * decisión explícita de quien está en pantalla, con el botón **Reintentar**.
 */
export function usePermisos(): Permisos {
  const consulta = useQuery({
    queryKey: clavesIdentidad.yo(),
    queryFn: obtenerYo,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  })

  const estado: EstadoDePermisos = consulta.isPending ? 'cargando' : consulta.isError ? 'error' : 'listo'

  return {
    estado,
    tiene: (permiso: CodigoPermiso) => estado === 'listo' && (consulta.data?.permisos.includes(permiso) ?? false),
    yo: consulta.data,
    error: consulta.error instanceof ErrorDeIdentidad ? consulta.error : undefined,
    reintentar: () => {
      void consulta.refetch()
    },
  }
}
