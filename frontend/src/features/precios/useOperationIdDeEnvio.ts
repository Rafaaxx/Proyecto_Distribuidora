import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'

/**
 * `Operation-Id` de un envío manual de precios (INV-06, change 13 tarea 12.2). El reintento del
 * usuario tras un error de red reenvía EXACTAMENTE la misma operación: el id se conserva
 * mientras el contenido no cambia y el envío no se completó. Se renueva cuando cambia el
 * contenido (otra operación) y después de `completar()` (pedir otra vez lo mismo, por ejemplo
 * regenerar el borrador, es otra operación). El contenido se compara por valor.
 *
 * `obtener` y `completar` se llaman desde manejadores de eventos, nunca durante el render.
 */
export function useOperationIdDeEnvio(contenido: unknown): { obtener: () => string; completar: () => void } {
  const clave = JSON.stringify(contenido)
  const actual = useRef<{ clave: string; id: string } | null>(null)

  return {
    obtener: () => {
      if (actual.current === null || actual.current.clave !== clave) {
        actual.current = { clave, id: generarOperationId() }
      }
      return actual.current.id
    },
    completar: () => {
      actual.current = null
    },
  }
}
