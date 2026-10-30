import { useQuery } from '@tanstack/react-query'

import { listarClientes } from '../clientes/api'
import { listarJornadas } from '../stock/api'
import { usePermisos } from './usePermisos'

/**
 * Lo que la pantalla necesita para los avisos de la baja de un usuario (change 20b, D6): las
 * jornadas no cerradas del usuario y cuántos clientes tiene asignados. Salen de las lecturas
 * existentes (`GET /stock/jornadas`, `GET /clientes?vendedor_id=`); `identidad` no importa `stock`
 * ni `clientes` en el backend. Cada lectura se pide solo si la sesión tiene el permiso de esa
 * lectura (ADR-027); sin él, el aviso no aparece y el servidor no rechaza la baja por eso.
 */

/** Tope de la lectura de clientes: con más, el aviso dice "más de 100". */
export const MAXIMO_DE_CLIENTES_CONTADOS = 100

export interface DatosParaAvisosDeBaja {
  jornadas: string[]
  clientesAsignados: number
  masDeLosContados: boolean
  cargando: boolean
}

export function useDatosParaAvisosDeBaja(usuarioId: string | undefined): DatosParaAvisosDeBaja {
  const { tiene } = usePermisos()
  const puedeVerJornadas = tiene('ABRIR_JORNADA') || tiene('RENDIR_JORNADA') || tiene('LIBERAR_UBICACION')
  const puedeVerClientes = tiene('GESTIONAR_CLIENTES')
  const hayUsuario = usuarioId !== undefined

  const jornadas = useQuery({
    queryKey: ['identidad', 'avisos-de-baja', 'jornadas', usuarioId ?? ''],
    queryFn: async () => {
      const [abiertas, enRendicion] = await Promise.all([
        listarJornadas({ usuarioId, estado: 'ABIERTA' }, undefined, 50),
        listarJornadas({ usuarioId, estado: 'EN_RENDICION' }, undefined, 50),
      ])
      return [...abiertas.items, ...enRendicion.items].map((jornada) => jornada.ubicacion_nombre)
    },
    enabled: hayUsuario && puedeVerJornadas,
    retry: false,
  })

  const clientes = useQuery({
    queryKey: ['identidad', 'avisos-de-baja', 'clientes', usuarioId ?? ''],
    queryFn: () => listarClientes({ vendedorId: usuarioId }, undefined, MAXIMO_DE_CLIENTES_CONTADOS),
    enabled: hayUsuario && puedeVerClientes,
    retry: false,
  })

  return {
    jornadas: jornadas.data ?? [],
    clientesAsignados: clientes.data?.items.length ?? 0,
    masDeLosContados: clientes.data?.cursor_siguiente != null,
    cargando: jornadas.isPending && jornadas.fetchStatus !== 'idle' ? true : clientes.isPending && clientes.fetchStatus !== 'idle',
  }
}
