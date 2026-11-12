import { useMutation, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from '../../../lib/api/httpClient'
import { CLAVE_CONSULTA_DISPOSITIVOS } from './useDispositivos'

async function revocarDispositivo(dispositivoId: string): Promise<void> {
  const respuesta = await apiFetch(`/identidad/dispositivos/${dispositivoId}`, { method: 'DELETE' })
  if (!respuesta.ok) {
    throw new Error('No se pudo revocar el dispositivo.')
  }
}

/** Tarea 13.5: revocar invalida la caché del listado para reflejar el
 * nuevo estado sin que la usuaria tenga que recargar la página. */
export function useRevocarDispositivo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: revocarDispositivo,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CONSULTA_DISPOSITIVOS })
    },
  })
}
