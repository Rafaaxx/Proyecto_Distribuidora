import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { detalleDeObservacion, etiquetaDeObservacion } from '../../../domain/revision/detalleDeObservacion'
import { ResolucionDeAviso } from './ResolucionDeAviso'

export interface ObservacionDeLaOperacion {
  codigo: string
  estado: string
  detalle?: { [clave: string]: unknown } | null
  resuelto_por_nombre?: string | null
  resuelto_en?: string | null
  comentario?: string | null
}

/**
 * Los avisos de una operación (compra, transferencia o ajuste) con su resolución, solo lectura (change 25,
 * tarea 15.2; D11; SYN-07, SYN-08). Sin avisos no muestra nada.
 */
export function ObservacionesDeLaOperacion({ observaciones }: { observaciones: readonly ObservacionDeLaOperacion[] }) {
  if (observaciones.length === 0) return null
  return (
    <Card className="flex flex-col gap-2 text-sm text-primary" data-testid="observaciones-de-la-operacion">
      <h2 className="text-base font-semibold">Observaciones</h2>
      {observaciones.map((observacion, indice) => (
        <p key={`${observacion.codigo}-${String(indice)}`} className="flex flex-wrap items-center gap-2">
          <Badge variante="negativo">{etiquetaDeObservacion(observacion.codigo)}</Badge>
          {detalleDeObservacion(observacion.codigo, observacion.detalle ?? null).map((linea) => (
            <span key={linea} className="text-primary/70">
              {linea}
            </span>
          ))}
          <ResolucionDeAviso observacion={observacion} />
        </p>
      ))}
    </Card>
  )
}
