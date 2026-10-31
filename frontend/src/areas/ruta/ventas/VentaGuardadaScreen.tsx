import { Link, useParams } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Card } from '../../../components/ui/Card'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { formatearFechaHora } from '../../../lib/fecha'
import { useVentaLocal } from '../datos/ventas'
import { NotaSinSenal } from './NotaSinSenal'
import { etiquetaDeEnvio } from './presentacionDeVentas'

const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

/**
 * Venta guardada en el teléfono (change 22a, tarea 10.3; `design.md` D13, D14; VTA-06): número
 * asignado al confirmar, total, estado de envío ("Sin enviar"), las acciones de la nota y "Nueva
 * venta". También es el detalle que abre "Ventas de hoy". Lee de Dexie, con o sin conexión.
 */
export function VentaGuardadaScreen() {
  const { id = '' } = useParams()
  const lectura = useVentaLocal(id)

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'no_encontrada') {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-primary">No encontramos esa venta en este teléfono.</p>
        <Link to="/ruta/ventas" className="text-sm underline">
          Ventas de hoy
        </Link>
      </div>
    )
  }

  const { venta } = lectura
  const cliente = venta.nota?.cliente.nombre ?? '—'
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold text-primary">Venta {venta.numero}</h1>
        <Ayuda clave="ruta.numeroDeVenta" />
        <span className="flex items-center gap-1">
          <Badge>{etiquetaDeEnvio(venta.estado_envio)}</Badge>
          <Ayuda clave="ruta.ventaSinEnviar" />
        </span>
      </div>
      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="break-words">{cliente}</p>
        <p className="text-xs text-primary/70">{formatearFechaHora(venta.occurred_at).trim()}</p>
        <p className="text-base font-semibold">{formatearDinero(venta.calculo.total)}</p>
      </Card>
      <NotaSinSenal venta={venta} />
      <div className="grid grid-cols-2 gap-2">
        <Link to="/ruta/vender" className={CLASE_ENLACE}>
          Nueva venta
        </Link>
        <Link to="/ruta/ventas" className={CLASE_ENLACE}>
          Ventas de hoy
        </Link>
      </div>
    </div>
  )
}

export default VentaGuardadaScreen
