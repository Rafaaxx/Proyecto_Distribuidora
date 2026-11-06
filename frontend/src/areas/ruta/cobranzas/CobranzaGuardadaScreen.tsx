import { Link, useParams } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import type { CobranzaLocal } from '../../../lib/dispositivo/db'
import { formatearFechaHora } from '../../../lib/fecha'
import { useCobranzaLocal } from '../datos/cobranzas'
import { useExplicacionDeOperacion } from '../datos/sincronizacion'
import { MarcaDeRechazoResuelto } from '../sincronizacion/MarcaDeRechazoResuelto'
import { claveDeAyudaDeEnvioDeCobranza, etiquetaDeEnvio } from '../ventas/presentacionDeVentas'

/**
 * Cobranza guardada en el teléfono (change 23, `design.md` D8, D9, D11; COB-01, COB-04, SYN-06,
 * SYN-07, SYN-09): cliente, importe, medios (con su referencia), observación, momento, estado de
 * envío y, si volvió con observaciones o rechazada, su explicación traducida por el tipo de
 * operación. Sin comprobante (COB-06 es de la etapa 2). Todo sale de Dexie, con o sin conexión.
 */
const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

export function CobranzaGuardadaScreen() {
  const { id = '' } = useParams()
  const lectura = useCobranzaLocal(id)

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'no_encontrada') {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-primary">No encontramos esa cobranza en este teléfono.</p>
        <Link to="/ruta/cobranzas" className="text-sm underline">
          Cobranzas de hoy
        </Link>
      </div>
    )
  }
  return <DetalleDeCobranza cobranza={lectura.cobranza} />
}

function textoDelMedio(cobranza: CobranzaLocal, medio: CobranzaLocal['medios'][number]): string {
  const nombre = cobranza.medios_nombres?.find((n) => n.medio_pago_id === medio.medio_pago_id)?.nombre ?? '—'
  const referencia = medio.referencia === null ? '' : ` · Referencia ${medio.referencia}`
  return `${nombre}: ${formatearDinero(medio.importe)}${referencia}`
}

function DetalleDeCobranza({ cobranza }: { cobranza: CobranzaLocal }) {
  const estado = cobranza.estado_envio ?? 'PENDIENTE'
  const explicacion = useExplicacionDeOperacion(cobranza.operation_id, estado)
  const claveDeEstado = claveDeAyudaDeEnvioDeCobranza(estado)
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold text-primary">Cobranza guardada</h1>
        <span className="flex items-center gap-1">
          <Badge variante={estado === 'RECHAZADA' ? 'negativo' : 'neutral'}>{etiquetaDeEnvio(estado)}</Badge>
          {claveDeEstado !== null && <Ayuda clave={claveDeEstado} />}
        </span>
        <MarcaDeRechazoResuelto operationId={cobranza.operation_id} estado={estado} conAyuda />
      </div>
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="break-words">{cobranza.cliente_nombre ?? '—'}</p>
        {cobranza.occurred_at !== undefined && <p className="text-xs text-primary/70">{formatearFechaHora(cobranza.occurred_at).trim()}</p>}
        <p className="text-base font-semibold">{formatearDinero(cobranza.total)}</p>
        <ul className="flex flex-col gap-1">
          {cobranza.medios.map((medio, i) => (
            <li key={i} className="break-words">
              {textoDelMedio(cobranza, medio)}
            </li>
          ))}
        </ul>
        {cobranza.observacion !== undefined && cobranza.observacion !== null && <p className="break-words">{cobranza.observacion}</p>}
      </Card>
      {explicacion?.tipo === 'rechazo' && (
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <h2 className="flex items-center gap-1 text-sm font-semibold">
            Motivo del rechazo
            <Ayuda clave="ruta.observacionesYRechazos" />
          </h2>
          <p className="break-words">{explicacion.texto}</p>
          {explicacion.codigo !== null && <p className="text-xs font-medium text-danger">{explicacion.codigo}</p>}
          <p className="text-xs text-primary/70">{explicacion.aviso}</p>
        </Card>
      )}
      {explicacion?.tipo === 'sin_detalle' && (
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <h2 className="flex items-center gap-1 text-sm font-semibold">
            Observaciones
            <Ayuda clave="ruta.observacionesYRechazos" />
          </h2>
          <p className="break-words">{explicacion.texto}</p>
        </Card>
      )}
      {explicacion?.tipo === 'observaciones' && (
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <h2 className="flex items-center gap-1 text-sm font-semibold">
            Observaciones
            <Ayuda clave="ruta.observacionesYRechazos" />
          </h2>
          <ul className="flex list-disc flex-col gap-1 pl-4">
            {explicacion.textos.map((texto, i) => (
              <li key={i} className="break-words">
                {texto}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Link to="/ruta/cobranzas" className={CLASE_ENLACE}>
        Cobranzas de hoy
      </Link>
    </div>
  )
}

export default CobranzaGuardadaScreen
