import { useQuery } from '@tanstack/react-query'

import { apiFetch } from '../../../lib/api/httpClient'

/** Forma de `DispositivoResponse` (`backend/app/modules/identidad/api.py`). */
export interface Dispositivo {
  id: string
  nombre: string
  prefijo: string
  estado: 'ACTIVO' | 'REVOCADO'
  ultimo_correlativo: number
  revocado_en: string | null
}

/**
 * Distingue "no tengo el permiso" de cualquier otro error, para que la
 * pantalla pueda mostrar el mensaje correcto sin adivinar leyendo el
 * `codigo` en el componente (tarea 13.5, SEG-06: ocultar en la interfaz es
 * cosmético, la validación real la hace el servidor en cada petición).
 */
export class PermisoRequeridoError extends Error {}

export const CLAVE_CONSULTA_DISPOSITIVOS = ['identidad', 'dispositivos'] as const

async function obtenerDispositivos(): Promise<Dispositivo[]> {
  const respuesta = await apiFetch('/identidad/dispositivos')

  if (respuesta.status === 403) {
    throw new PermisoRequeridoError('No tenés permiso para gestionar dispositivos.')
  }
  if (!respuesta.ok) {
    throw new Error('No se pudieron obtener los dispositivos.')
  }

  return (await respuesta.json()) as Dispositivo[]
}

export function useDispositivos() {
  return useQuery({
    queryKey: CLAVE_CONSULTA_DISPOSITIVOS,
    queryFn: obtenerDispositivos,
  })
}
