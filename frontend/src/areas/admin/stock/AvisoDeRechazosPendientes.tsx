import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { TEXTO_SIN_PERMISO_DE_REVISION, textoDeRechazosPendientes } from '../../../domain/stock/rendicion'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

/**
 * El aviso de las operaciones rechazadas sin resolver de una jornada (change 25, tarea 15.3; D9 = B, D12; RUT-05,
 * SEG-06). Mientras haya alguna, la jornada no se rinde. Con `REVISAR_OBSERVACIONES` lleva a «Rechazadas» filtrada
 * por la jornada; sin ese permiso dice quién las resuelve y no ofrece el acceso. La cantidad llega con la jornada:
 * no se pide ninguna lista.
 */
export function AvisoDeRechazosPendientes({ cantidad, jornadaId }: { cantidad: number; jornadaId: string }) {
  return (
    <Alert className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span>{textoDeRechazosPendientes(cantidad)}</span>
      <Ayuda clave="stock.rechazadasDeLaJornada" />
      <SiTienePermiso
        permiso="REVISAR_OBSERVACIONES"
        fallback={<span>{TEXTO_SIN_PERMISO_DE_REVISION}</span>}
      >
        <Link to={`/admin/revision/rechazadas?jornada=${jornadaId}`} className="font-medium underline">
          Ver rechazadas
        </Link>
      </SiTienePermiso>
    </Alert>
  )
}
