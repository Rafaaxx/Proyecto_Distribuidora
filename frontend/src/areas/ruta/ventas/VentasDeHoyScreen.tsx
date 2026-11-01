import { Link } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { useVentasDeHoy } from '../datos/ventas'
import { ayudasDeProblemasEnLista, etiquetaDeEnvio } from './presentacionDeVentas'

/**
 * Ventas de hoy (change 22a, tarea 11.1; spec `ruta/area-de-ruta`; `design.md` D14; SYN-09,
 * RUT-04): las ventas del teléfono de la jornada abierta, leídas de Dexie con o sin conexión.
 * Cada una abre su detalle con las acciones de la nota. Sin lógica de negocio.
 */
export function VentasDeHoyScreen() {
  const datos = useVentasDeHoy()

  if (datos.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (datos.estado === 'sin_datos') {
    return <p className="text-sm text-primary">Todavía no hay datos descargados. Abrí una jornada desde el inicio.</p>
  }

  const claves = ayudasDeProblemasEnLista(datos.ventas.map((v) => v.estado_envio))

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h1 className="text-lg font-semibold text-primary">Ventas de hoy</h1>
      {datos.ventas.length === 0 ? (
        <p className="text-sm text-primary">Todavía no hiciste ventas en esta jornada.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {datos.ventas.map((venta) => (
            <li key={venta.venta_id} className="rounded-md border border-border bg-surface">
              <Link to={`/ruta/ventas/${venta.venta_id}`} className="flex min-w-0 flex-col gap-1 p-3">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-primary">{venta.numero}</span>
                  <span className="text-sm font-semibold text-primary">{formatearDinero(venta.calculo.total)}</span>
                </span>
                <span className="break-words text-sm text-primary">{venta.nota?.cliente.nombre ?? '—'}</span>
                <span>
                  <Badge>{etiquetaDeEnvio(venta.estado_envio)}</Badge>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="flex flex-wrap items-center gap-1 text-xs text-primary/70">
        Las ventas sin enviar se guardan en el teléfono. <Ayuda clave="ruta.ventaSinEnviar" />
        {claves.map((clave) => (
          <Ayuda key={clave} clave={clave} />
        ))}
      </p>
    </div>
  )
}

export default VentasDeHoyScreen
