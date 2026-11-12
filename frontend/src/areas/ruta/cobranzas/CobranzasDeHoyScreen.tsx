import { Link } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useCobranzasDeHoy } from '../datos/cobranzas'
import { useRechazosResueltos } from '../datos/rechazosResueltos'
import { MarcaDeRechazoResuelto } from '../sincronizacion/MarcaDeRechazoResuelto'
import { hayRechazoResuelto } from '../sincronizacion/presentacion'
import { ayudasDeProblemasEnListaDeCobranzas, etiquetaDeEnvio } from '../ventas/presentacionDeVentas'

/**
 * Cobranzas de hoy (change 23, `design.md` D8; SYN-09, COB-04): las cobranzas independientes del
 * teléfono en la jornada abierta, leídas de Dexie con o sin conexión. Cada una abre su detalle.
 * Sin lógica de negocio.
 */
export function CobranzasDeHoyScreen() {
  const datos = useCobranzasDeHoy()
  const resueltos = useRechazosResueltos()

  if (datos.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (datos.estado === 'sin_datos') {
    return <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
  }

  const claves = ayudasDeProblemasEnListaDeCobranzas(datos.cobranzas.map((c) => c.estado_envio ?? 'PENDIENTE'))

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h1 className="text-lg font-semibold text-primary">Cobranzas de hoy</h1>
      {datos.cobranzas.length === 0 ? (
        <p className="text-sm text-primary">Todavía no hiciste cobranzas en esta jornada.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {datos.cobranzas.map((cobranza) => (
            <li key={cobranza.cobranza_id} className="rounded-md border border-border bg-surface">
              <Link to={`/ruta/cobranzas/${cobranza.cobranza_id}`} className="flex min-w-0 flex-col gap-1 p-3">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="break-words text-sm font-semibold text-primary">{cobranza.cliente_nombre ?? '—'}</span>
                  <span className="text-sm font-semibold text-primary">{formatearDinero(cobranza.total)}</span>
                </span>
                {cobranza.occurred_at !== undefined && (
                  <span className="text-xs text-primary/70">{formatearFechaHora(cobranza.occurred_at).trim()}</span>
                )}
                <span className="flex flex-wrap items-center gap-2">
                  <Badge variante={cobranza.estado_envio === 'RECHAZADA' ? 'negativo' : 'neutral'}>
                    {etiquetaDeEnvio(cobranza.estado_envio ?? 'PENDIENTE')}
                  </Badge>
                  <MarcaDeRechazoResuelto operationId={cobranza.operation_id} estado={cobranza.estado_envio ?? 'PENDIENTE'} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="flex flex-wrap items-center gap-1 text-xs text-primary/70">
        {claves.map((clave) => (
          <Ayuda key={clave} clave={clave} />
        ))}
        {hayRechazoResuelto(
          resueltos,
          datos.cobranzas.map((c) => ({ operationId: c.operation_id, estado: c.estado_envio ?? 'PENDIENTE' })),
        ) && <Ayuda clave="ruta.rechazoResuelto" />}
      </p>
    </div>
  )
}

export default CobranzasDeHoyScreen
