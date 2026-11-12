import { useState } from 'react'

import { generarOperationId } from '../../lib/api/operationId'

/**
 * `Operation-Id` que se conserva mientras el contenido a enviar no cambia y se renueva
 * cuando cambia (INV-06, `design.md` D10 / spec `administracion-de-compras`): el reintento
 * del usuario tras un error de red reenvía EXACTAMENTE la misma operación; editar el
 * formulario es otra operación y necesita otro id. Compara el contenido por valor
 * (`JSON.stringify`), no por referencia, así un re-render con un objeto equivalente no
 * lo renueva.
 */
export function useOperationIdPorContenido(contenido: unknown): string {
  const clave = JSON.stringify(contenido)
  const [estado, setEstado] = useState(() => ({ clave, id: generarOperationId() }))
  if (estado.clave === clave) return estado.id
  const nuevo = { clave, id: generarOperationId() }
  setEstado(nuevo)
  return nuevo.id
}
