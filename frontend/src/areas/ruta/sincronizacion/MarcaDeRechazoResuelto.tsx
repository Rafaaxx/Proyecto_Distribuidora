import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import type { EstadoDeEnvio } from '../../../lib/dispositivo/db'
import { useRechazosResueltos } from '../datos/rechazosResueltos'

/**
 * Marca «Resuelta por administración» junto a «Rechazada» (change 25, D8; SYN-09): solo si la
 * operación está rechazada y su `operation_id` figura en los rechazos resueltos del último
 * bootstrap. `conAyuda` agrega la «?» en los detalles; en las listas (dentro de un enlace) la
 * ayuda va aparte, al pie. Sin lógica de negocio.
 */
export function MarcaDeRechazoResuelto({
  operationId,
  estado,
  conAyuda = false,
}: {
  operationId: string
  estado: EstadoDeEnvio
  conAyuda?: boolean
}) {
  const resueltos = useRechazosResueltos()
  if (estado !== 'RECHAZADA' || !resueltos.has(operationId)) return null
  return (
    <span className="flex items-center gap-1">
      <Badge>Resuelta por administración</Badge>
      {conAyuda && <Ayuda clave="ruta.rechazoResuelto" />}
    </span>
  )
}
